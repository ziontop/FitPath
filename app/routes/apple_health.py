"""Apple Health integration routes."""
from __future__ import annotations

import hashlib
import json
import secrets
import string
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import bearer_token_user, current_user, utcnow
from ..models import ApiSyncToken, HealthImportBatch, User
from ..schemas import AppleHealthDeleteIn, AppleHealthTokenCreateIn, ShortcutSyncIn
from ..services.apple_health import (
    RESULT_TYPES,
    SUPPORTED_TYPES,
    candidates_from_shortcut,
    import_candidates,
    parse_export_file,
    preview_export,
    safe_delete_imported,
)

router = APIRouter(prefix="/api/integrations/apple-health", tags=["apple-health"])


def _parse_types(raw: list[str] | None) -> set[str]:
    if not raw:
        return set(SUPPORTED_TYPES)
    values: list[str] = []
    for item in raw:
        try:
            parsed = json.loads(item)
            if isinstance(parsed, list):
                values.extend(str(v) for v in parsed)
                continue
        except json.JSONDecodeError:
            pass
        values.append(item)
    selected = {v.strip() for v in values if v.strip()}
    bad = selected - SUPPORTED_TYPES
    if bad:
        raise HTTPException(status_code=422, detail="unsupported Apple Health type")
    return selected


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> dict:
    await file.seek(0)
    return preview_export(file.filename or "export", file.file)


@router.post("/import")
async def import_export(
    file: UploadFile = File(...),
    types: list[str] | None = Form(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    selected = _parse_types(types)
    await file.seek(0)
    candidates, _, _, invalid = parse_export_file(file.file)
    result = import_candidates(db, user, candidates, selected, "export")
    if invalid:
        result["totals"]["invalid"] += invalid
        batch = db.get(HealthImportBatch, result["batch_id"])
        if batch is not None:
            batch.records_invalid += invalid
            batch.status = "partial"
            result["status"] = "partial"
    return result


@router.get("/imports")
def list_imports(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(HealthImportBatch)
        .where(HealthImportBatch.user_id == user.id, HealthImportBatch.provider == "apple_health")
        .order_by(HealthImportBatch.created_at.desc())
        .limit(100)
    ).all()
    return {"items": [_batch_public(row) for row in rows]}


@router.delete("/data")
def delete_data(
    body: AppleHealthDeleteIn | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    types = set(body.types) if body and body.types else None
    return safe_delete_imported(
        db,
        user.id,
        types,
        body.from_ if body else None,
        body.to if body else None,
    )


@router.post("/tokens", status_code=201)
def create_token(
    body: AppleHealthTokenCreateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    token, prefix, digest = _new_token()
    row = ApiSyncToken(
        user_id=user.id,
        name=body.name,
        prefix=prefix,
        token_hash=digest,
        expires_at=utcnow() + timedelta(days=body.expires_in_days) if body.expires_in_days else None,
    )
    db.add(row)
    db.flush()
    return {**_token_public(row), "token": token}


@router.get("/tokens")
def list_tokens(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(ApiSyncToken).where(ApiSyncToken.user_id == user.id).order_by(ApiSyncToken.created_at.desc())
    ).all()
    return {"items": [_token_public(row) for row in rows]}


@router.post("/tokens/{token_id}/rotate")
def rotate_token(
    token_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = _owned_token(db, token_id, user.id)
    token, prefix, digest = _new_token()
    row.prefix = prefix
    row.token_hash = digest
    row.revoked_at = None
    row.last_used_at = None
    db.flush()
    return {**_token_public(row), "token": token}


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(
    token_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = _owned_token(db, token_id, user.id)
    row.revoked_at = utcnow()
    db.flush()
    return Response(status_code=204)


@router.post("/shortcut")
def shortcut_sync(
    body: ShortcutSyncIn,
    user: User = Depends(bearer_token_user),
    db: Session = Depends(get_db),
) -> dict:
    result = import_candidates(db, user, candidates_from_shortcut(body), set(SUPPORTED_TYPES), "shortcut")
    return {
        "batch_id": result["batch_id"],
        "applied": {
            t: result["results"][t]["inserted"] + result["results"][t]["updated"]
            for t in RESULT_TYPES
        },
        "skipped": {t: result["results"][t]["skipped"] for t in RESULT_TYPES},
        "invalid": {t: result["results"][t]["invalid"] for t in RESULT_TYPES},
        "conflict": {t: result["results"][t]["conflict"] for t in RESULT_TYPES},
    }


def _batch_public(row: HealthImportBatch) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "status": row.status,
        "date_range": {
            "start": row.date_start.isoformat() if row.date_start else None,
            "end": row.date_end.isoformat() if row.date_end else None,
        },
        "records_inserted": row.records_inserted,
        "records_updated": row.records_updated,
        "records_skipped": row.records_skipped,
        "records_invalid": row.records_invalid,
        "records_conflict": row.records_conflict,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "error": row.error,
    }


def _new_token() -> tuple[str, str, str]:
    alphabet = string.ascii_letters + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(10))
    prefix = f"fpk_{suffix}"
    token = f"{prefix}_{secrets.token_urlsafe(32)}"
    return token, prefix, hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token_public(row: ApiSyncToken) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.prefix,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


def _owned_token(db: Session, token_id: int, user_id: int) -> ApiSyncToken:
    row = db.get(ApiSyncToken, token_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="token not found")
    return row
