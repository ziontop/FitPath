"""SQLAlchemy 2.0 typed declarative models for the multi-user FitPath app.

Every table that holds user data is scoped by a ``user_id`` foreign key. Parent
child relationships (workout session -> set logs, program -> days -> exercises)
use ``ON DELETE CASCADE`` at the database level plus ORM ``cascade`` so a delete
propagates cleanly. All datetime/date columns use native Python types so the
backend can run range queries without string juggling.

This module is import-safe and has no side effects at import time.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Single declarative base shared by every model and by Alembic."""


# ---------------------------------------------------------------------------
# Identity & auth
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    profile: Mapped[Optional["Profile"]] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    auth_sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AuthSession(Base):
    """Server-side session store backing the httpOnly session cookie."""

    __tablename__ = "auth_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="auth_sessions")


# ---------------------------------------------------------------------------
# Profile (1:1 with user)
# ---------------------------------------------------------------------------
class Profile(Base):
    __tablename__ = "profile"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(120))
    sex: Mapped[str] = mapped_column(String(16), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    activity_level: Mapped[str] = mapped_column(
        String(24), nullable=False, default="moderate"
    )
    goal: Mapped[str] = mapped_column(String(16), nullable=False, default="maintain")
    training_goal: Mapped[str] = mapped_column(
        String(24), nullable=False, default="hypertrophy"
    )
    experience_level: Mapped[str] = mapped_column(
        String(24), nullable=False, default="beginner"
    )
    days_per_week: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    equipment: Mapped[str] = mapped_column(
        String(24), nullable=False, default="full_gym"
    )
    units: Mapped[str] = mapped_column(String(16), nullable=False, default="metric")
    wake_time: Mapped[str] = mapped_column(String(5), nullable=False, default="07:00")
    water_goal_ml: Mapped[int] = mapped_column(Integer, nullable=False, default=2500)
    step_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=8000)
    exercise_goal_min: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )

    user: Mapped["User"] = relationship(back_populates="profile")


# ---------------------------------------------------------------------------
# Nutrition / health logs (user-scoped)
# ---------------------------------------------------------------------------
class MealLog(Base):
    __tablename__ = "meal_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kcal: Mapped[float] = mapped_column(Float, nullable=False)
    eaten_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="snack")
    protein_g: Mapped[Optional[float]] = mapped_column(Float)
    carbs_g: Mapped[Optional[float]] = mapped_column(Float)
    fat_g: Mapped[Optional[float]] = mapped_column(Float)
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_meal_log_user_eaten", "user_id", "eaten_at"),)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    activity: Mapped[str] = mapped_column(String(120), nullable=False)
    minutes: Mapped[float] = mapped_column(Float, nullable=False)
    intensity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="moderate"
    )
    done_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    __table_args__ = (Index("ix_activity_log_user_done", "user_id", "done_at"),)


class SleepLog(Base):
    __tablename__ = "sleep_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    wake_time: Mapped[str] = mapped_column(String(5), nullable=False)
    logged_for: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    __table_args__ = (Index("ix_sleep_log_user_day", "user_id", "logged_for"),)


class StepLog(Base):
    __tablename__ = "step_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    steps: Mapped[int] = mapped_column(Integer, nullable=False)
    logged_for: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "logged_for", name="uq_step_log_user_day"),
    )


class WaterLog(Base):
    __tablename__ = "water_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ml: Mapped[int] = mapped_column(Integer, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    __table_args__ = (Index("ix_water_log_user_at", "user_id", "logged_at"),)


class WeightLog(Base):
    __tablename__ = "weight_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    logged_for: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "logged_for", name="uq_weight_log_user_day"),
    )


# ---------------------------------------------------------------------------
# Generic health integration provenance
# ---------------------------------------------------------------------------
class ApiSyncToken(Base):
    """Personal bearer token for provider push integrations."""

    __tablename__ = "api_sync_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (Index("ix_api_sync_token_user", "user_id"),)


class HealthImportBatch(Base):
    """One health import run, either export-file or push-sync."""

    __tablename__ = "health_import_batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="apple_health")
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_conflict: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    date_start: Mapped[Optional[date]] = mapped_column(Date)
    date_end: Mapped[Optional[date]] = mapped_column(Date)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (Index("ix_health_import_batch_user", "user_id", "created_at"),)


class ImportedHealthRecord(Base):
    """Provenance link for idempotency, update detection, and safe delete."""

    __tablename__ = "imported_health_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="apple_health")
    resource_type: Mapped[str] = mapped_column(String(24), nullable=False)
    external_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_payload: Mapped[str] = mapped_column(Text, nullable=False)
    local_resource_type: Mapped[str] = mapped_column(String(24), nullable=False)
    local_resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("health_import_batch.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "resource_type",
            "external_key",
            name="uq_imported_health_record",
        ),
        Index("ix_imported_health_record_user_type", "user_id", "provider", "resource_type"),
    )


# ---------------------------------------------------------------------------
# Exercise catalog (seeded reference data + optional per-user custom rows)
# ---------------------------------------------------------------------------
class Exercise(Base):
    __tablename__ = "exercise"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)  # compound|isolation
    primary_muscle: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    secondary_muscles: Mapped[Optional[str]] = mapped_column(Text)  # JSON-encoded list
    equipment: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    is_main_lift: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True
    )

    set_logs: Mapped[list["SetLog"]] = relationship(back_populates="exercise")
    program_exercises: Mapped[list["ProgramExercise"]] = relationship(
        back_populates="exercise"
    )


# ---------------------------------------------------------------------------
# Workouts & performance tracking
# ---------------------------------------------------------------------------
class WorkoutSession(Base):
    __tablename__ = "workout_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(120))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    program_day_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("program_day.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    sets: Mapped[list["SetLog"]] = relationship(
        back_populates="workout_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SetLog.set_index",
    )
    program_day: Mapped[Optional["ProgramDay"]] = relationship(
        back_populates="workout_sessions"
    )

    __table_args__ = (Index("ix_workout_session_user_date", "user_id", "date"),)


class SetLog(Base):
    __tablename__ = "set_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_session.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercise.id"), index=True, nullable=False
    )
    set_index: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    rpe: Mapped[Optional[float]] = mapped_column(Float)
    is_warmup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    workout_session: Mapped["WorkoutSession"] = relationship(back_populates="sets")
    exercise: Mapped["Exercise"] = relationship(back_populates="set_logs")


# ---------------------------------------------------------------------------
# Generated workout programs
# ---------------------------------------------------------------------------
class Program(Base):
    __tablename__ = "program"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    training_goal: Mapped[str] = mapped_column(String(24), nullable=False)
    split_type: Mapped[str] = mapped_column(String(32), nullable=False)
    days_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, index=True, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    days: Mapped[list["ProgramDay"]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProgramDay.day_index",
    )

    __table_args__ = (Index("ix_program_user_active", "user_id", "active"),)


class ProgramDay(Base):
    __tablename__ = "program_day"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), index=True, nullable=False
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    program: Mapped["Program"] = relationship(back_populates="days")
    exercises: Mapped[list["ProgramExercise"]] = relationship(
        back_populates="program_day",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProgramExercise.order_index",
    )
    workout_sessions: Mapped[list["WorkoutSession"]] = relationship(
        back_populates="program_day"
    )


class ProgramExercise(Base):
    __tablename__ = "program_exercise"

    id: Mapped[int] = mapped_column(primary_key=True)
    program_day_id: Mapped[int] = mapped_column(
        ForeignKey("program_day.id", ondelete="CASCADE"), index=True, nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercise.id"), index=True, nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    target_sets: Mapped[int] = mapped_column(Integer, nullable=False)
    target_reps: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. "6-10"
    target_rpe: Mapped[Optional[float]] = mapped_column(Float)
    rest_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    progression: Mapped[Optional[str]] = mapped_column(String(32))

    program_day: Mapped["ProgramDay"] = relationship(back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship(back_populates="program_exercises")


# ---------------------------------------------------------------------------
# Generated nutrition plan
# ---------------------------------------------------------------------------
class NutritionPlan(Base):
    __tablename__ = "nutrition_plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    goal: Mapped[str] = mapped_column(String(16), nullable=False)
    target_kcal: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g: Mapped[int] = mapped_column(Integer, nullable=False)
    carbs_g: Mapped[int] = mapped_column(Integer, nullable=False)
    fat_g: Mapped[int] = mapped_column(Integer, nullable=False)
    meals_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, index=True, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_nutrition_plan_user_active", "user_id", "active"),)


__all__ = [
    "Base",
    "User",
    "AuthSession",
    "Profile",
    "MealLog",
    "ActivityLog",
    "SleepLog",
    "StepLog",
    "WaterLog",
    "WeightLog",
    "ApiSyncToken",
    "HealthImportBatch",
    "ImportedHealthRecord",
    "Exercise",
    "WorkoutSession",
    "SetLog",
    "Program",
    "ProgramDay",
    "ProgramExercise",
    "NutritionPlan",
]
