
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.user_preference import UserPreference
from app.schemas.user_preference import (
    UserPreferenceResponse,
    UserPreferenceUpdate,
)


router = APIRouter(
    prefix="/users/me/preferences",
    tags=["User preferences"],
)


@router.get("/", response_model=UserPreferenceResponse)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preferences = db.get(UserPreference, current_user.id)

    if preferences is None:
        preferences = UserPreference(user_id=current_user.id)
        try:
            db.add(preferences)
            db.commit()
            db.refresh(preferences)
        except Exception:
            db.rollback()
            raise

    return preferences


@router.patch("/", response_model=UserPreferenceResponse)
def update_preferences(
    data: UserPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preferences = db.get(UserPreference, current_user.id)

    try:
        if preferences is None:
            preferences = UserPreference(user_id=current_user.id)
            db.add(preferences)
            db.flush()

        changes = data.model_dump(exclude_unset=True)

        for field, value in changes.items():
            setattr(preferences, field, value)

        db.commit()
        db.refresh(preferences)
    except Exception:
        db.rollback()
        raise

    return preferences
