from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
_tmp.close()
os.environ["FITPATH_DB"] = _tmp.name

import app.db as db_module  # noqa: E402

db_module.DB_PATH = Path(_tmp.name)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.deps import utcnow  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    ActivityLog,
    ApiSyncToken,
    HealthImportBatch,
    ImportedHealthRecord,
    MealLog,
    SleepLog,
    StepLog,
    WaterLog,
    WeightLog,
)


def csrf_headers(client: TestClient) -> dict:
    token = client.cookies.get("fitpath_csrf")
    return {"X-CSRF-Token": token} if token else {}


def make_user(client: TestClient) -> dict:
    uid = uuid.uuid4().hex[:10]
    r = client.post(
        "/api/auth/register",
        json={"email": f"{uid}@ex.com", "username": f"u{uid}", "password": "password123"},
    )
    assert r.status_code == 201, r.text
    return r.json()["user"]


def export_xml(steps: int = 1200, water: int = 500) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count"
          startDate="2026-07-14 08:00:00 -0700" endDate="2026-07-14 08:10:00 -0700" value="{steps}"/>
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Apple Watch" unit="count"
          startDate="2026-07-14 09:00:00 -0700" endDate="2026-07-14 09:05:00 -0700" value="800"/>
  <Record type="HKQuantityTypeIdentifierBodyMass" sourceName="Withings" unit="kg"
          startDate="2026-07-14 06:30:00 -0700" endDate="2026-07-14 06:30:00 -0700" value="80.1"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepCore"
          startDate="2026-07-13 23:30:00 -0700" endDate="2026-07-14 03:00:00 -0700"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepREM"
          startDate="2026-07-14 03:00:00 -0700" endDate="2026-07-14 06:45:00 -0700"/>
  <Record type="HKQuantityTypeIdentifierDietaryWater" sourceName="iPhone" unit="mL"
          startDate="2026-07-14 10:00:00 -0700" endDate="2026-07-14 10:00:00 -0700" value="{water}"/>
  <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="32" durationUnit="min"
           totalEnergyBurned="320" totalEnergyBurnedUnit="kcal"
           startDate="2026-07-14 06:30:00 -0700" endDate="2026-07-14 07:02:00 -0700" sourceName="Apple Watch"/>
</HealthData>""".encode()


def export_zip(xml: bytes | None = None, member: str = "apple_health_export/export.xml") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, xml if xml is not None else export_xml())
    return buf.getvalue()


def upload(client: TestClient, path: str, data: bytes, headers: dict | None = None):
    return client.post(
        path,
        files={"file": ("export.zip", data, "application/zip")},
        headers=headers or {},
    )


def test_preview_is_stateless_and_import_is_idempotent():
    with TestClient(app) as client:
        make_user(client)
        h = csrf_headers(client)
        data = export_zip()

        preview = upload(client, "/api/integrations/apple-health/preview", data, h)
        assert preview.status_code == 200, preview.text
        assert preview.json()["counts_by_type"]["steps"] == 1
        assert client.get("/api/integrations/apple-health/imports").json()["items"] == []

        first = upload(client, "/api/integrations/apple-health/import", data, h)
        assert first.status_code == 200, first.text
        assert first.json()["totals"]["inserted"] == 5

        second = upload(client, "/api/integrations/apple-health/import", data, h)
        assert second.status_code == 200, second.text
        assert second.json()["totals"]["skipped"] == 5

        assert len(client.get("/api/logs/steps").json()["items"]) == 1
        assert len(client.get("/api/logs/water", params={"date": "2026-07-14"}).json()["items"]) == 1


def test_manual_edit_preserved_and_safe_delete_keeps_modified_rows():
    with TestClient(app) as client:
        user = make_user(client)
        h = csrf_headers(client)
        assert upload(client, "/api/integrations/apple-health/import", export_zip(), h).status_code == 200

        with db_module.SessionLocal() as db:
            step = db.scalar(select(StepLog).where(StepLog.user_id == user["id"]))
            step.steps = 9999
            db.commit()

        changed = upload(client, "/api/integrations/apple-health/import", export_zip(export_xml(steps=1500)), h)
        assert changed.status_code == 200, changed.text
        assert changed.json()["results"]["steps"]["conflict"] == 1
        assert client.get("/api/logs/steps").json()["items"][0]["steps"] == 9999

        deleted = client.request(
            "DELETE",
            "/api/integrations/apple-health/data",
            json={"types": ["steps", "water"]},
            headers=h,
        )
        assert deleted.status_code == 200, deleted.text
        body = deleted.json()
        assert body["preserved_modified"]["steps"] == 1
        assert body["deleted"]["water"] == 1
        assert client.get("/api/logs/steps").json()["items"][0]["steps"] == 9999
        assert client.get("/api/logs/water", params={"date": "2026-07-14"}).json()["items"] == []
        with db_module.SessionLocal() as db:
            assert db.scalar(select(ImportedHealthRecord).where(ImportedHealthRecord.user_id == user["id"], ImportedHealthRecord.resource_type == "steps")) is None


def test_untrusted_upload_defenses_zip_slip_bomb_and_xxe():
    with TestClient(app) as client:
        make_user(client)
        h = csrf_headers(client)

        slip = upload(client, "/api/integrations/apple-health/preview", export_zip(member="../apple_health_export/export.xml"), h)
        assert slip.status_code == 400

        bomb_xml = ("<HealthData><!--" + ("A" * 100_000) + "--></HealthData>").encode()
        bomb = upload(client, "/api/integrations/apple-health/preview", export_zip(bomb_xml), h)
        assert bomb.status_code == 400

        xxe = b"""<?xml version="1.0"?><!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]><HealthData>&xxe;</HealthData>"""
        bad = client.post(
            "/api/integrations/apple-health/preview",
            files={"file": ("export.xml", xxe, "application/xml")},
            headers=h,
        )
        assert bad.status_code == 400


def test_upload_parser_rejects_dtds_and_zip_bombs_before_opening_member():
    with TestClient(app) as client:
        make_user(client)
        h = csrf_headers(client)

        dtd_only = b'<?xml version="1.0"?><!DOCTYPE HealthData><HealthData></HealthData>'
        dtd = client.post(
            "/api/integrations/apple-health/preview",
            files={"file": ("export.xml", dtd_only, "application/xml")},
            headers=h,
        )
        assert dtd.status_code == 400, dtd.text

        highly_compressible = ("<HealthData><!--" + ("A" * 100_000) + "--></HealthData>").encode()
        bomb = export_zip(highly_compressible)
        with patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("zip member should not be opened")):
            rejected = upload(client, "/api/integrations/apple-health/preview", bomb, h)
        assert rejected.status_code == 400, rejected.text


def test_shortcut_is_bearer_only_and_token_hash_not_returned_in_list():
    with TestClient(app) as client:
        make_user(client)
        h = csrf_headers(client)
        created = client.post(
            "/api/integrations/apple-health/tokens",
            json={"name": "iPhone", "expires_in_days": 30},
            headers=h,
        )
        assert created.status_code == 201, created.text
        token = created.json()["token"]
        assert "token" not in client.get("/api/integrations/apple-health/tokens").json()["items"][0]

        payload = {"steps": [{"date": "2026-07-15", "count": 4321}]}
        assert client.post("/api/integrations/apple-health/shortcut", json=payload).status_code == 401
        ok = client.post(
            "/api/integrations/apple-health/shortcut",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["applied"]["steps"] == 1

        revoked = client.delete(f"/api/integrations/apple-health/tokens/{created.json()['id']}", headers=h)
        assert revoked.status_code == 204
        assert client.post(
            "/api/integrations/apple-health/shortcut",
            json={"steps": [{"date": "2026-07-16", "count": 1}]},
            headers={"Authorization": f"Bearer {token}"},
        ).status_code == 401


def test_shortcut_ignores_cookies_and_enforces_expired_tokens():
    with TestClient(app) as client:
        make_user(client)
        h = csrf_headers(client)
        created = client.post(
            "/api/integrations/apple-health/tokens",
            json={"name": "Shortcut", "expires_in_days": 30},
            headers=h,
        )
        assert created.status_code == 201, created.text
        token = created.json()["token"]

        with db_module.SessionLocal() as db:
            row = db.get(ApiSyncToken, created.json()["id"])
            assert row is not None
            assert row.token_hash != token
            assert len(row.token_hash) == 64

        payload = {"steps": [{"date": "2026-07-17", "count": 3210}]}
        cookie_only = client.post("/api/integrations/apple-health/shortcut", json=payload, headers=h)
        assert cookie_only.status_code == 401

        ok = client.post(
            "/api/integrations/apple-health/shortcut",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok.status_code == 200, ok.text

        with db_module.SessionLocal() as db:
            row = db.get(ApiSyncToken, created.json()["id"])
            assert row is not None
            row.expires_at = utcnow() - timedelta(seconds=1)
            db.commit()

        expired = client.post(
            "/api/integrations/apple-health/shortcut",
            json={"steps": [{"date": "2026-07-18", "count": 1}]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert expired.status_code == 401


def test_d5_import_scope_includes_supported_types_and_excludes_energy_macros():
    nutrition = b"""
  <Record type="HKQuantityTypeIdentifierDietaryEnergyConsumed" unit="kcal"
          startDate="2026-07-14 12:00:00 -0700" endDate="2026-07-14 12:00:00 -0700" value="650"/>
  <Record type="HKQuantityTypeIdentifierDietaryProtein" unit="g"
          startDate="2026-07-14 12:00:00 -0700" endDate="2026-07-14 12:00:00 -0700" value="42"/>
"""
    xml = export_xml().replace(b"</HealthData>", nutrition + b"</HealthData>")
    with TestClient(app) as client:
        user = make_user(client)
        h = csrf_headers(client)
        imported = upload(client, "/api/integrations/apple-health/import", export_zip(xml), h)
        assert imported.status_code == 200, imported.text
        assert imported.json()["totals"]["inserted"] == 5
        assert imported.json()["results"]["steps"]["inserted"] == 1
        assert imported.json()["results"]["weight"]["inserted"] == 1
        assert imported.json()["results"]["sleep"]["inserted"] == 1
        assert imported.json()["results"]["water"]["inserted"] == 1
        assert imported.json()["results"]["workouts"]["inserted"] == 1

        with db_module.SessionLocal() as db:
            assert db.scalar(select(StepLog).where(StepLog.user_id == user["id"])) is not None
            assert db.scalar(select(WeightLog).where(WeightLog.user_id == user["id"])) is not None
            assert db.scalar(select(SleepLog).where(SleepLog.user_id == user["id"])) is not None
            assert db.scalar(select(WaterLog).where(WaterLog.user_id == user["id"])) is not None
            assert db.scalar(select(ActivityLog).where(ActivityLog.user_id == user["id"])) is not None
            assert db.scalar(select(MealLog).where(MealLog.user_id == user["id"])) is None


def test_d3_api_routes_are_not_shadowed_by_spa_fallback():
    with TestClient(app) as client:
        make_user(client)
        h = csrf_headers(client)
        routes = [
            client.post("/api/integrations/apple-health/preview", headers=h),
            client.post("/api/integrations/apple-health/import", headers=h),
            client.get("/api/integrations/apple-health/imports"),
            client.request("DELETE", "/api/integrations/apple-health/data", json={}, headers=h),
            client.post("/api/integrations/apple-health/tokens", json={}, headers=h),
            client.get("/api/integrations/apple-health/tokens"),
            client.post("/api/integrations/apple-health/tokens/999999/rotate", headers=h),
            client.delete("/api/integrations/apple-health/tokens/999999", headers=h),
            client.post("/api/integrations/apple-health/shortcut", json={}),
        ]
        for response in routes:
            assert "application/json" in response.headers.get("content-type", "")
            assert "<!doctype html" not in response.text.lower()


def test_frontend_fixture_zip_layout_and_multipart_type_shape_are_accepted():
    fixture = Path("tests") / "fixtures" / "apple_health" / "minimal_export.zip"
    with zipfile.ZipFile(fixture) as zf:
        assert zf.namelist() == ["apple_health_export/export.xml"]
    data = fixture.read_bytes()

    with TestClient(app) as client:
        make_user(client)
        h = csrf_headers(client)
        preview = client.post(
            "/api/integrations/apple-health/preview",
            files={"file": ("minimal_export.zip", data, "application/zip")},
            headers=h,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["counts_by_type"] == {
            "steps": 1,
            "weight": 1,
            "sleep": 1,
            "water": 1,
            "workouts": 1,
        }

        imported = client.post(
            "/api/integrations/apple-health/import",
            files={"file": ("minimal_export.zip", data, "application/zip")},
            data={"types": json.dumps(["steps", "water"])},
            headers=h,
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["totals"]["inserted"] == 2
        assert imported.json()["results"]["steps"]["inserted"] == 1
        assert imported.json()["results"]["water"]["inserted"] == 1


def test_admin_reset_clears_import_provenance_but_keeps_tokens():
    with TestClient(app) as client:
        user = make_user(client)
        h = csrf_headers(client)
        token = client.post("/api/integrations/apple-health/tokens", json={"name": "iPhone"}, headers=h)
        assert token.status_code == 201
        assert upload(client, "/api/integrations/apple-health/import", export_zip(), h).status_code == 200

        reset = client.post("/api/admin/reset", headers=h)
        assert reset.status_code == 200
        with db_module.SessionLocal() as db:
            assert db.scalar(select(HealthImportBatch).where(HealthImportBatch.user_id == user["id"])) is None
            assert db.scalar(select(ImportedHealthRecord).where(ImportedHealthRecord.user_id == user["id"])) is None
            assert db.scalar(select(WaterLog).where(WaterLog.user_id == user["id"])) is None
        assert client.get("/api/integrations/apple-health/tokens").json()["items"]
