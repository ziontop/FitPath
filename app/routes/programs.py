"""Workout program routes (contract §7, ``/api/programs``).

Thin router over :mod:`app.services.programs`. Static paths (``/generate``,
``/active``, ``/today``) are declared before ``/{program_id}`` so they are not
captured by the int path parameter.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import ProgramGenerateIn, ProgramUpdate
from ..services import programs

router = APIRouter(prefix="/api/programs", tags=["programs"])


def _program_or_404(db: Session, program_id: int, user_id: int):
    program = programs.get_program(db, program_id, user_id)
    if program is None:
        raise HTTPException(status_code=404, detail="program not found")
    return program


@router.post("/generate", status_code=201)
def generate(
    body: Optional[ProgramGenerateIn] = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    body = body or ProgramGenerateIn()
    program = programs.generate_program(
        db,
        user,
        training_goal=body.training_goal,
        days_per_week=body.days_per_week,
        experience=body.experience,
        equipment=body.equipment,
    )
    return programs.program_detail(program)


@router.get("")
def list_all(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    rows = programs.list_programs(db, user.id)
    return {"items": [programs.program_summary(p) for p in rows]}


@router.get("/active")
def get_active(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    program = programs.active_program(db, user.id)
    if program is None:
        raise HTTPException(status_code=404, detail="no active program")
    return programs.program_detail(program)


@router.get("/today")
def get_today(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    return programs.today_workout(db, user)


@router.get("/{program_id}")
def get_one(
    program_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    program = _program_or_404(db, program_id, user.id)
    return programs.program_detail(program)


@router.put("/{program_id}")
def update_one(
    program_id: int,
    body: ProgramUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    program = _program_or_404(db, program_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        program.name = data["name"]
    if "active" in data and data["active"] is not None:
        if data["active"]:
            programs.activate(db, program)
        else:
            program.active = False
    db.flush()
    program = _program_or_404(db, program_id, user.id)
    return programs.program_detail(program)


@router.delete("/{program_id}")
def delete_one(
    program_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    program = _program_or_404(db, program_id, user.id)
    db.delete(program)  # cascades to days -> exercises
    return {"ok": True}
