from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.db import models
from app.db.base import session
from app.schemas.settings import Profile

router = APIRouter(tags=["settings"])


def load_profile() -> Profile:
    with session() as s:
        row = s.get(models.Profile, 1)
        return Profile.model_validate(row.data) if row else Profile()


@router.get("/settings", response_model=Profile)
def get_settings() -> Profile:
    return load_profile()


@router.put("/settings", response_model=Profile)
def put_settings(profile: Profile) -> Profile:
    with session() as s:
        row = s.get(models.Profile, 1)
        data: dict[str, Any] = profile.model_dump()
        if row is None:
            s.add(models.Profile(id=1, data=data))
        else:
            row.data = data
    return profile
