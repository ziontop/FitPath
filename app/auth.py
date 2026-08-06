"""Authentication: argon2 password hashing, server-side sessions, auth routes.

Sessions are stored server-side in :class:`~app.models.AuthSession` and keyed by
an opaque, httpOnly ``fitpath_session`` cookie. A companion JS-readable
``fitpath_csrf`` cookie carries the CSRF token (validated by
:class:`app.security.CSRFMiddleware` on every mutating request).
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    SESSION_MAX_AGE_DAYS,
    SESSION_MAX_AGE_SECONDS,
    cookie_secure,
    current_user,
    utcnow,
)
from .models import AuthSession, User
from .schemas import LoginIn, RegisterIn

# argon2 (recommended parameters) per the API contract.
hasher = PasswordHash.recommended()

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_public(u: User) -> dict:
    """Public user shape: ``{id, email, username, created_at}`` (contract §1)."""
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _create_session(db: Session, user_id: int) -> AuthSession:
    sess = AuthSession(
        token=secrets.token_urlsafe(32),
        csrf_token=secrets.token_urlsafe(32),
        user_id=user_id,
        expires_at=utcnow() + timedelta(days=SESSION_MAX_AGE_DAYS),
    )
    db.add(sess)
    db.flush()
    return sess


def set_auth_cookies(response: Response, sess: AuthSession) -> None:
    secure = cookie_secure()
    response.set_cookie(
        SESSION_COOKIE,
        sess.token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        sess.csrf_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/register", status_code=201)
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    existing = db.scalar(
        select(User).where(or_(User.email == email, User.username == body.username))
    )
    if existing is not None:
        detail = (
            "email already registered"
            if existing.email == email
            else "username already taken"
        )
        raise HTTPException(status_code=409, detail=detail)

    user = User(
        email=email,
        username=body.username,
        password_hash=hasher.hash(body.password),
    )
    db.add(user)
    db.flush()
    db.refresh(user)  # populate server-generated created_at

    sess = _create_session(db, user.id)
    set_auth_cookies(response, sess)
    return {"user": user_public(user)}


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> dict:
    identifier = body.identifier.strip()
    user = db.scalar(
        select(User).where(
            or_(User.email == identifier.lower(), User.username == identifier)
        )
    )
    if user is None or not hasher.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    sess = _create_session(db, user.id)
    set_auth_cookies(response, sess)
    return {"user": user_public(user)}


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token == token))
    resp = Response(status_code=204)
    clear_auth_cookies(resp)
    return resp


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"user": user_public(user)}
