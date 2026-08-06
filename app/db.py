"""SQLAlchemy engine/session infrastructure for the multi-user FitPath app.

The single-user raw ``sqlite3`` helpers (``connect`` / ``SCHEMA`` / ``_migrate``)
have been replaced by a SQLAlchemy engine + session factory. Routes obtain a
``Session`` through the :func:`get_db` FastAPI dependency, and schema management
lives in Alembic (``init_db`` remains as a convenience for dev/tests).

The database location is read from the ``FITPATH_DB`` environment variable and
falls back to ``<repo>/fitpath.sqlite3``. This module is import-safe.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .models import Base

# Repo root is two levels up: app/db.py -> app -> <repo>.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _REPO_ROOT / "fitpath.sqlite3"


def resolve_db_path() -> Path:
    """Absolute path to the SQLite file (``FITPATH_DB`` env var or default)."""
    env_path = os.getenv("FITPATH_DB")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return _DEFAULT_DB_PATH


def database_url() -> str:
    """SQLAlchemy URL for the configured SQLite database."""
    return f"sqlite:///{resolve_db_path().as_posix()}"


# Resolved once at import; the verification script and app set FITPATH_DB before
# importing this module. Alembic recomputes the URL at runtime via database_url().
DB_PATH: Path = resolve_db_path()
DATABASE_URL: str = database_url()

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    # NullPool hands every Session/checkout a brand-new SQLite connection and
    # disposes it on close, instead of reusing a small pool of long-lived
    # connections. Under WAL, a pooled connection can keep serving a stale read
    # snapshot after another connection has committed, which caused fresh-login
    # -> GET /api/auth/me 401s, just-created workouts 404-ing on add-set, and a
    # just-favorited meal missing from /recent. A fresh connection per request
    # always sees the latest committed data.
    poolclass=NullPool,
    future=True,
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    """Per-connection SQLite pragmas.

    - foreign_keys=ON enforces FKs incl. ON DELETE CASCADE.
    - journal_mode=WAL + a busy_timeout let multiple processes (e.g. concurrent
      persona/demo clients) read and write the same DB file without immediate
      "database is locked" errors (writers wait up to the timeout).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a Session, commit on success, rollback on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables from the models. For dev/tests; prod uses Alembic."""
    Base.metadata.create_all(engine)


__all__ = [
    "Base",
    "DB_PATH",
    "DATABASE_URL",
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    "resolve_db_path",
    "database_url",
]
