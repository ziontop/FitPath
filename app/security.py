"""CSRF protection middleware (double-submit + server-side validation).

For every mutating request (``POST``/``PUT``/``PATCH``/``DELETE``) that carries
a valid session, the ``X-CSRF-Token`` header must equal the session's stored
``csrf_token``; otherwise the request is rejected with ``403``. Safe methods
(``GET``/``HEAD``/``OPTIONS``) and the login/register endpoints are exempt.

Requests without a valid session are passed through untouched so the normal
``current_user`` dependency can return the appropriate ``401``.
"""
from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .db import SessionLocal
from .deps import CSRF_HEADER, SESSION_COOKIE, load_valid_session

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/integrations/apple-health/shortcut",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        if token:
            db = SessionLocal()
            try:
                sess = load_valid_session(db, token)
            finally:
                db.close()
            if sess is not None:
                header = request.headers.get(CSRF_HEADER)
                if not header or not secrets.compare_digest(header, sess.csrf_token):
                    return JSONResponse(
                        {"detail": "invalid or missing CSRF token"}, status_code=403
                    )

        return await call_next(request)
