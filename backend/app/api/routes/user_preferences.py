
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

DEFAULT_PREFERENCES = {
    "theme": "system",
    "language": "es",
    "push_notifications": False,
}


def build_preferences_response(
    preferences: UserPreference,
) -> UserPreferenceResponse:
    configured = preferences.preferences or {}
    values = {
        **DEFAULT_PREFERENCES,
        **configured,
    }
    return UserPreferenceResponse(
        user_id=preferences.user_id,
        theme=values["theme"],
        language=values["language"],
        email_notifications=preferences.email_notifications,
        push_notifications=values["push_notifications"],
        updated_at=preferences.updated_at,
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

    return build_preferences_response(preferences)


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
        preference_changes = {
            key: changes.pop(key)
            for key in ("theme", "language", "push_notifications")
            if key in changes
        }

        if preference_changes:
            preferences.preferences = {
                **(preferences.preferences or {}),
                **preference_changes,
            }

        if "email_notifications" in changes:
            preferences.email_notifications = changes["email_notifications"]

        db.commit()
        db.refresh(preferences)
    except Exception:
        db.rollback()
        raise

    return build_preferences_response(preferences)
