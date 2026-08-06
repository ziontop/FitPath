"""Apple Health import parsing, idempotent writes, and safe deletion."""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import BinaryIO, Iterable

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    ActivityLog,
    HealthImportBatch,
    ImportedHealthRecord,
    SleepLog,
    StepLog,
    User,
    WaterLog,
    WeightLog,
)

PROVIDER = "apple_health"
SUPPORTED_TYPES = {"steps", "weight", "sleep", "water", "workouts"}
RESULT_TYPES = ("steps", "weight", "sleep", "water", "workouts")
STATES = ("inserted", "updated", "skipped", "invalid", "conflict")
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_XML_BYTES = 3 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_RECORDS = 5_000_000
MAX_PARSE_SECONDS = 120


class UnsafeExportError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    resource_type: str
    external_key: str
    payload: dict
    local_type: str
    local_date: date


def empty_counts() -> dict:
    return {t: {s: 0 for s in STATES} for t in RESULT_TYPES}


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def payload_hash(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def parse_apple_datetime(value: str) -> datetime:
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
    return dt.astimezone(dt.tzinfo).replace(tzinfo=None)


def _parse_iso_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(value.tzinfo).replace(tzinfo=None)
    return value


def _humanize_workout(raw: str) -> str:
    name = raw.removeprefix("HKWorkoutActivityType")
    mapping = {
        "Running": "Running",
        "TrackAndField": "Running",
        "Walking": "Walking",
        "Hiking": "Walking",
        "Cycling": "Cycling",
        "Swimming": "Swimming",
        "TraditionalStrengthTraining": "Strength",
        "FunctionalStrengthTraining": "Strength",
        "HighIntensityIntervalTraining": "HIIT",
        "Yoga": "Yoga",
        "Pilates": "Yoga",
        "FlexibilityTraining": "Yoga",
        "Cooldown": "Yoga",
        "MindAndBody": "Yoga",
    }
    if name in mapping:
        return mapping[name]
    return re.sub(r"(?<!^)([A-Z])", r" \1", name).strip() or "Workout"


def _default_intensity(activity: str) -> str:
    if activity in {"Yoga", "Walking", "Flexibility", "Cooldown"}:
        return "light"
    if activity in {"Running", "HIIT", "Stair Climbing"}:
        return "vigorous"
    return "moderate"


def _date_range(candidates: Iterable[Candidate]) -> dict:
    days = [c.local_date for c in candidates]
    if not days:
        return {"start": None, "end": None}
    return {"start": min(days).isoformat(), "end": max(days).isoformat()}


def _valid_not_future(day: date) -> bool:
    return day <= date.today() + timedelta(days=1)


def _file_size(fileobj: BinaryIO) -> int:
    pos = fileobj.tell()
    fileobj.seek(0, io.SEEK_END)
    size = fileobj.tell()
    fileobj.seek(pos)
    return size


@contextmanager
def _open_xml_stream(fileobj: BinaryIO):
    fileobj.seek(0)
    if _file_size(fileobj) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload too large")
    magic = fileobj.read(2)
    fileobj.seek(0)
    if magic != b"PK":
        yield fileobj
        return

    try:
        zf = zipfile.ZipFile(fileobj)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="malformed Apple Health export") from exc
    try:
        target = None
        for info in zf.infolist():
            normalized = info.filename.replace("\\", "/")
            if normalized.endswith("apple_health_export/export.xml"):
                target = info
                break
        if target is None:
            raise HTTPException(status_code=422, detail="Apple Health export.xml not found")
        normalized = target.filename.replace("\\", "/")
        if normalized.startswith("/") or "/../" in f"/{normalized}" or normalized.endswith("/"):
            raise HTTPException(status_code=400, detail="unsafe archive member")
        if target.file_size > MAX_XML_BYTES:
            raise HTTPException(status_code=413, detail="Apple Health export too large")
        compressed = max(target.compress_size, 1)
        if target.file_size / compressed > MAX_COMPRESSION_RATIO:
            raise HTTPException(status_code=400, detail="unsafe archive compression ratio")
        with zf.open(target) as member:
            yield member
    finally:
        zf.close()


def _iter_elements(xml_stream: BinaryIO):
    started = time.monotonic()
    count = 0
    try:
        for _, elem in SafeET.iterparse(xml_stream, events=("end",), forbid_dtd=True):
            if elem.tag not in {"Record", "Workout"}:
                elem.clear()
                continue
            count += 1
            if count > MAX_RECORDS or time.monotonic() - started > MAX_PARSE_SECONDS:
                raise HTTPException(status_code=413, detail="Apple Health export exceeds processing limits")
            attrs = dict(elem.attrib)
            tag = elem.tag
            elem.clear()
            yield tag, attrs
    except DefusedXmlException as exc:
        raise HTTPException(status_code=400, detail="unsafe XML content") from exc
    except SafeET.ParseError as exc:
        raise HTTPException(status_code=400, detail="malformed Apple Health XML") from exc


def parse_export(data: bytes) -> tuple[list[Candidate], dict, list[str], int]:
    return parse_export_file(io.BytesIO(data))


def parse_export_file(fileobj: BinaryIO) -> tuple[list[Candidate], dict, list[str], int]:
    steps_by_day_source: dict[date, dict[str, int]] = {}
    weight_by_day: dict[date, tuple[datetime, float]] = {}
    water_by_day: dict[date, int] = {}
    sleep_by_day: dict[date, list[tuple[datetime, datetime]]] = {}
    workouts: list[Candidate] = []
    units: dict[str, set[str]] = {"weight": set(), "water": set()}
    warnings: list[str] = []
    invalid = 0

    with _open_xml_stream(fileobj) as xml_stream:
        for tag, a in _iter_elements(xml_stream):
            try:
                if tag == "Record":
                    rtype = a.get("type")
                    if rtype == "HKQuantityTypeIdentifierStepCount":
                        unit = a.get("unit")
                        end = parse_apple_datetime(a["endDate"])
                        day = end.date()
                        val = int(float(a["value"]))
                        if unit != "count" or val < 0 or val > 200_000 or not _valid_not_future(day):
                            invalid += 1
                            continue
                        source = a.get("sourceName") or "Unknown"
                        steps_by_day_source.setdefault(day, {})[source] = steps_by_day_source.setdefault(day, {}).get(source, 0) + val
                    elif rtype == "HKQuantityTypeIdentifierBodyMass":
                        unit = a.get("unit")
                        units["weight"].add(unit or "")
                        end = parse_apple_datetime(a["endDate"])
                        kg = float(a["value"])
                        if unit == "lb":
                            kg *= 0.45359237
                        elif unit != "kg":
                            invalid += 1
                            continue
                        kg = round(kg, 1)
                        if not (20 < kg < 400) or not _valid_not_future(end.date()):
                            invalid += 1
                            continue
                        day = end.date()
                        if day not in weight_by_day or end > weight_by_day[day][0]:
                            weight_by_day[day] = (end, kg)
                    elif rtype == "HKQuantityTypeIdentifierDietaryWater":
                        unit = a.get("unit")
                        units["water"].add(unit or "")
                        end = parse_apple_datetime(a["endDate"])
                        ml = float(a["value"])
                        if unit == "fl_oz_us":
                            ml *= 29.5735
                        elif unit != "mL":
                            invalid += 1
                            continue
                        day = end.date()
                        ml_i = int(round(ml))
                        if ml_i <= 0 or not _valid_not_future(day):
                            invalid += 1
                            continue
                        water_by_day[day] = water_by_day.get(day, 0) + ml_i
                    elif rtype == "HKCategoryTypeIdentifierSleepAnalysis":
                        value = a.get("value", "")
                        asleep = value.endswith(("AsleepCore", "AsleepDeep", "AsleepREM", "AsleepUnspecified", "Asleep"))
                        if not asleep:
                            continue
                        start = parse_apple_datetime(a["startDate"])
                        end = parse_apple_datetime(a["endDate"])
                        if end <= start or not _valid_not_future(end.date()):
                            invalid += 1
                            continue
                        sleep_by_day.setdefault(end.date(), []).append((start, end))
                elif tag == "Workout":
                    start = parse_apple_datetime(a["startDate"])
                    end = parse_apple_datetime(a["endDate"])
                    activity = _humanize_workout(a.get("workoutActivityType", "Workout"))
                    dur = float(a.get("duration") or 0)
                    if a.get("durationUnit") == "s":
                        dur /= 60
                    minutes = round(dur)
                    if minutes <= 0 and end > start:
                        minutes = round((end - start).total_seconds() / 60)
                    if minutes <= 0 or minutes > 1440 or not _valid_not_future(start.date()):
                        invalid += 1
                        continue
                    intensity = _default_intensity(activity)
                    kcal = a.get("totalEnergyBurned")
                    if kcal:
                        rate = float(kcal) / minutes
                        intensity = "light" if rate < 5 else "moderate" if rate <= 10 else "vigorous"
                    source = a.get("sourceName") or "Unknown"
                    payload = {
                        "activity": activity,
                        "minutes": float(minutes),
                        "intensity": intensity,
                        "done_at": start.isoformat(),
                    }
                    key = f"{activity}|{source}|{start.isoformat()}|{end.isoformat()}"
                    workouts.append(Candidate("workouts", key, payload, "activity_log", start.date()))
            except (KeyError, ValueError, OverflowError):
                invalid += 1

    candidates: list[Candidate] = []
    for day, by_source in steps_by_day_source.items():
        source, steps = max(by_source.items(), key=lambda item: item[1])
        if len(by_source) > 1:
            warnings.append("Steps: multiple sources per day; dominant source was used.")
        candidates.append(Candidate("steps", day.isoformat(), {"steps": steps}, "step_log", day))
    for day, (_, kg) in weight_by_day.items():
        candidates.append(Candidate("weight", day.isoformat(), {"kg": kg}, "weight_log", day))
    for day, intervals in sleep_by_day.items():
        merged = _merge_intervals(intervals)
        minutes = sum((end - start).total_seconds() for start, end in merged) / 60
        hours = round(min(minutes / 60, 24), 2)
        if hours < 0 or hours > 24:
            invalid += 1
            continue
        wake_time = max(end for _, end in intervals).strftime("%H:%M")
        candidates.append(Candidate("sleep", day.isoformat(), {"hours": hours, "wake_time": wake_time}, "sleep_log", day))
    for day, ml in water_by_day.items():
        if ml > 5000:
            ml = 5000
            warnings.append("Water: daily total exceeded 5000 mL and was capped.")
        candidates.append(Candidate("water", day.isoformat(), {"ml": ml}, "water_log", day))
    candidates.extend(workouts)
    return candidates, {k: sorted(v) for k, v in units.items() if v}, warnings, invalid


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def preview_export(filename: str, data_or_file) -> dict:
    if isinstance(data_or_file, (bytes, bytearray)):
        candidates, units, warnings, invalid = parse_export(bytes(data_or_file))
    else:
        candidates, units, warnings, invalid = parse_export_file(data_or_file)
    counts = {t: 0 for t in RESULT_TYPES}
    samples = {t: [] for t in RESULT_TYPES}
    for c in candidates:
        counts[c.resource_type] += 1
        if len(samples[c.resource_type]) < 3:
            samples[c.resource_type].append(_sample(c))
    if invalid:
        warnings.append(f"{invalid} records were invalid and will be skipped on import.")
    return {
        "filename": filename,
        "date_range": _date_range(candidates),
        "counts_by_type": counts,
        "units_detected": units,
        "samples": samples,
        "warnings": warnings,
    }


def _sample(c: Candidate) -> dict:
    if c.resource_type == "steps":
        return {"date": c.external_key, "value": c.payload["steps"]}
    if c.resource_type == "weight":
        return {"date": c.external_key, "kg": c.payload["kg"]}
    if c.resource_type == "sleep":
        return {"wake_date": c.external_key, **c.payload}
    if c.resource_type == "water":
        return {"date": c.external_key, "ml": c.payload["ml"]}
    return {
        "activity": c.payload["activity"],
        "date": c.local_date.isoformat(),
        "minutes": c.payload["minutes"],
        "intensity": c.payload["intensity"],
    }


def candidates_from_shortcut(body) -> list[Candidate]:
    candidates: list[Candidate] = []
    for row in body.steps:
        candidates.append(Candidate("steps", row.date.isoformat(), {"steps": row.count}, "step_log", row.date))
    for row in body.weight:
        candidates.append(Candidate("weight", row.date.isoformat(), {"kg": round(row.kg, 1)}, "weight_log", row.date))
    for row in body.sleep:
        candidates.append(Candidate("sleep", row.date.isoformat(), {"hours": row.hours, "wake_time": row.wake_time}, "sleep_log", row.date))
    for row in body.water:
        candidates.append(Candidate("water", row.date.isoformat(), {"ml": row.ml}, "water_log", row.date))
    for row in body.workouts:
        start = _parse_iso_datetime(row.start)
        end = _parse_iso_datetime(row.end) if row.end else start + timedelta(minutes=row.minutes)
        key = f"{row.activity}|{row.source}|{start.isoformat()}|{end.isoformat()}"
        payload = {
            "activity": row.activity,
            "minutes": float(row.minutes),
            "intensity": row.intensity,
            "done_at": start.isoformat(),
        }
        candidates.append(Candidate("workouts", key, payload, "activity_log", start.date()))
    return candidates


def import_candidates(db: Session, user: User, candidates: list[Candidate], selected: set[str], source: str) -> dict:
    counts = empty_counts()
    batch = HealthImportBatch(user_id=user.id, provider=PROVIDER, source=source, status="running")
    db.add(batch)
    db.flush()

    for c in candidates:
        if c.resource_type not in selected:
            continue
        if not _candidate_valid(c):
            counts[c.resource_type]["invalid"] += 1
            continue
        _apply_candidate(db, user.id, batch.id, c, counts)

    totals = {s: sum(counts[t][s] for t in RESULT_TYPES) for s in STATES}
    batch.records_inserted = totals["inserted"]
    batch.records_updated = totals["updated"]
    batch.records_skipped = totals["skipped"]
    batch.records_invalid = totals["invalid"]
    batch.records_conflict = totals["conflict"]
    days = [c.local_date for c in candidates if c.resource_type in selected]
    batch.date_start = min(days) if days else None
    batch.date_end = max(days) if days else None
    batch.status = "partial" if totals["invalid"] or totals["conflict"] else "completed"
    batch.completed_at = datetime.now()
    db.flush()
    return {
        "batch_id": batch.id,
        "source": source,
        "status": batch.status,
        "date_range": _date_range([c for c in candidates if c.resource_type in selected]),
        "results": counts,
        "totals": totals,
    }


def _candidate_valid(c: Candidate) -> bool:
    if not _valid_not_future(c.local_date):
        return False
    p = c.payload
    if c.resource_type == "steps":
        return 0 <= int(p["steps"]) <= 200_000
    if c.resource_type == "weight":
        return 20 < float(p["kg"]) < 400
    if c.resource_type == "sleep":
        return 0 <= float(p["hours"]) <= 24 and re.match(r"^\d{2}:\d{2}$", p["wake_time"]) is not None
    if c.resource_type == "water":
        return 1 <= int(p["ml"]) <= 5000
    if c.resource_type == "workouts":
        return 0 < float(p["minutes"]) <= 1440 and p["intensity"] in {"light", "moderate", "vigorous"}
    return False


def _apply_candidate(db: Session, user_id: int, batch_id: int, c: Candidate, counts: dict) -> None:
    payload_json = canonical_json(c.payload)
    h = payload_hash(payload_json)
    prov = db.scalar(
        select(ImportedHealthRecord).where(
            ImportedHealthRecord.user_id == user_id,
            ImportedHealthRecord.provider == PROVIDER,
            ImportedHealthRecord.resource_type == c.resource_type,
            ImportedHealthRecord.external_key == c.external_key,
        )
    )
    if prov is None:
        if c.resource_type in {"steps", "weight"} and _existing_day_row(db, user_id, c) is not None:
            counts[c.resource_type]["conflict"] += 1
            return
        local = _insert_local(db, user_id, c)
        db.flush()
        db.add(ImportedHealthRecord(
            user_id=user_id, provider=PROVIDER, resource_type=c.resource_type,
            external_key=c.external_key, payload_hash=h, imported_payload=payload_json,
            local_resource_type=c.local_type, local_resource_id=local.id, batch_id=batch_id,
        ))
        counts[c.resource_type]["inserted"] += 1
        return

    if h == prov.payload_hash:
        counts[c.resource_type]["skipped"] += 1
        return
    local = _get_local(db, user_id, prov.local_resource_type, prov.local_resource_id)
    if local is None:
        local = _insert_local(db, user_id, c)
        db.flush()
        prov.local_resource_type = c.local_type
        prov.local_resource_id = local.id
        prov.imported_payload = payload_json
        prov.payload_hash = h
        prov.batch_id = batch_id
        counts[c.resource_type]["inserted"] += 1
    elif _local_payload(local, prov.local_resource_type) == json.loads(prov.imported_payload):
        _update_local(local, c)
        prov.imported_payload = payload_json
        prov.payload_hash = h
        prov.batch_id = batch_id
        counts[c.resource_type]["updated"] += 1
    else:
        counts[c.resource_type]["conflict"] += 1


def _existing_day_row(db: Session, user_id: int, c: Candidate):
    model = StepLog if c.resource_type == "steps" else WeightLog
    return db.scalar(select(model).where(model.user_id == user_id, model.logged_for == c.local_date))


def _insert_local(db: Session, user_id: int, c: Candidate):
    p = c.payload
    if c.resource_type == "steps":
        row = StepLog(user_id=user_id, steps=int(p["steps"]), logged_for=c.local_date)
    elif c.resource_type == "weight":
        row = WeightLog(user_id=user_id, weight_kg=float(p["kg"]), logged_for=c.local_date)
    elif c.resource_type == "sleep":
        row = SleepLog(user_id=user_id, hours=float(p["hours"]), wake_time=p["wake_time"], logged_for=c.local_date)
    elif c.resource_type == "water":
        row = WaterLog(user_id=user_id, ml=int(p["ml"]), logged_at=datetime.combine(c.local_date, dt_time(12, 0)))
    else:
        row = ActivityLog(user_id=user_id, activity=p["activity"], minutes=float(p["minutes"]), intensity=p["intensity"], done_at=datetime.fromisoformat(p["done_at"]))
    db.add(row)
    return row


def _update_local(row, c: Candidate) -> None:
    p = c.payload
    if c.resource_type == "steps":
        row.steps = int(p["steps"])
    elif c.resource_type == "weight":
        row.weight_kg = float(p["kg"])
    elif c.resource_type == "sleep":
        row.hours = float(p["hours"])
        row.wake_time = p["wake_time"]
    elif c.resource_type == "water":
        row.ml = int(p["ml"])
    else:
        row.activity = p["activity"]
        row.minutes = float(p["minutes"])
        row.intensity = p["intensity"]
        row.done_at = datetime.fromisoformat(p["done_at"])


def _get_local(db: Session, user_id: int, local_type: str, local_id: int):
    models = {
        "step_log": StepLog, "weight_log": WeightLog, "sleep_log": SleepLog,
        "water_log": WaterLog, "activity_log": ActivityLog,
    }
    model = models.get(local_type)
    if model is None:
        return None
    row = db.get(model, local_id)
    return row if row is not None and row.user_id == user_id else None


def _local_payload(row, local_type: str) -> dict:
    if local_type == "step_log":
        return {"steps": row.steps}
    if local_type == "weight_log":
        return {"kg": row.weight_kg}
    if local_type == "sleep_log":
        return {"hours": row.hours, "wake_time": row.wake_time}
    if local_type == "water_log":
        return {"ml": row.ml}
    return {
        "activity": row.activity,
        "minutes": row.minutes,
        "intensity": row.intensity,
        "done_at": row.done_at.isoformat(),
    }


def safe_delete_imported(db: Session, user_id: int, types: set[str] | None, from_date: date | None, to_date: date | None) -> dict:
    deleted = {t: 0 for t in RESULT_TYPES}
    preserved = {t: 0 for t in RESULT_TYPES}
    removed = 0
    stmt = select(ImportedHealthRecord).where(ImportedHealthRecord.user_id == user_id, ImportedHealthRecord.provider == PROVIDER)
    if types:
        stmt = stmt.where(ImportedHealthRecord.resource_type.in_(types))
    for prov in db.scalars(stmt).all():
        local = _get_local(db, user_id, prov.local_resource_type, prov.local_resource_id)
        local_day = _row_date(local, prov.local_resource_type) if local is not None else None
        if (from_date and local_day and local_day < from_date) or (to_date and local_day and local_day > to_date):
            continue
        if local is not None and _local_payload(local, prov.local_resource_type) == json.loads(prov.imported_payload):
            db.delete(local)
            deleted[prov.resource_type] += 1
        elif local is not None:
            preserved[prov.resource_type] += 1
        db.delete(prov)
        removed += 1
    return {"deleted": deleted, "preserved_modified": preserved, "provenance_removed": removed}


def _row_date(row, local_type: str) -> date:
    if local_type in {"step_log", "weight_log", "sleep_log"}:
        return row.logged_for
    if local_type == "water_log":
        return row.logged_at.date()
    return row.done_at.date()
