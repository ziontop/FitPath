"""Shared FastAPI dependencies and low-level auth primitives.

This module is intentionally dependency-light (it imports only ``db`` and
``models``) so both :mod:`app.auth` and :mod:`app.security` can build on it
without creating an import cycle.
"""
from __future__ import annotations

import os
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ApiSyncToken, AuthSession, User

# Cookie / header names (contract §1).
SESSION_COOKIE = "fitpath_session"
CSRF_COOKIE = "fitpath_csrf"
CSRF_HEADER = "X-CSRF-Token"

# ~30-day sessions.
SESSION_MAX_AGE_DAYS = 30
SESSION_MAX_AGE_SECONDS = SESSION_MAX_AGE_DAYS * 24 * 3600


def cookie_secure() -> bool:
    """Whether to set the ``Secure`` cookie flag (env ``FITPATH_COOKIE_SECURE``)."""
    return os.getenv("FITPATH_COOKIE_SECURE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def utcnow() -> datetime:
    """Naive UTC ``datetime`` (matches how SQLite stores ``func.now()``)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def load_valid_session(db: Session, token: Optional[str]) -> Optional[AuthSession]:
    """Return a non-expired :class:`AuthSession` for ``token`` or ``None``."""
    if not token:
        return None
    sess = db.scalar(select(AuthSession).where(AuthSession.token == token))
    if sess is None:
        return None
    if sess.expires_at <= utcnow():
        return None
    return sess


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the authenticated user from the session cookie, else 401."""
    token = request.cookies.get(SESSION_COOKIE)
    sess = load_valid_session(db, token)
    if sess is None:
        raise HTTPException(status_code=401, detail="authentication required")
    user = db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def bearer_token_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve user from Authorization: Bearer only; never uses cookies."""
    auth = request.headers.get("Authorization") or ""
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="bearer token required")
    parts = token.split("_", 2)
    if len(parts) != 3 or parts[0] != "fpk" or not parts[1] or not parts[2]:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    prefix = f"fpk_{parts[1]}"
    row = db.scalar(select(ApiSyncToken).where(ApiSyncToken.prefix == prefix))
    now = utcnow()
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if (
        row is None
        or row.revoked_at is not None
        or (row.expires_at is not None and row.expires_at <= now)
        or not secrets.compare_digest(digest, row.token_hash)
    ):
        raise HTTPException(status_code=401, detail="invalid bearer token")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    row.last_used_at = now
    db.flush()
    return user
