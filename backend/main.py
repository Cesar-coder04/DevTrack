from fastapi import FastAPI

from app.api.projects import router as projects_router
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.user_work_items import router as user_work_items_router
from app.api.routes.organizations import router as organizations_router
from app.api.routes.organization_members import (
    router as organization_members_router,
)
from app.api.routes.organization_projects import (
    router as organization_projects_router,
)
from app.api.routes.project_members import router as project_members_router
from app.api.routes.work_items import router as work_items_router
from app.api.routes.work_item_comments import router as work_item_comments_router
from app.api.routes.tags import router as tags_router
from app.api.routes.work_item_tags import router as work_item_tags_router
from app.api.routes.work_item_history import router as work_item_history_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.work_item_attachments import (
    router as work_item_attachments_router,
)
from app.api.routes.user_preferences import (
    router as user_preferences_router,
)
from app.api.routes.user_sessions import router as user_sessions_router
from app.api.routes.organization_invitations import (
    router as organization_invitations_router,
)

app = FastAPI(title="DevTrack API")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(user_work_items_router)
app.include_router(projects_router)
app.include_router(organizations_router)
app.include_router(organization_members_router)
app.include_router(organization_projects_router)
app.include_router(project_members_router)
app.include_router(work_items_router)
app.include_router(work_item_comments_router)
app.include_router(tags_router)
app.include_router(work_item_tags_router)
app.include_router(work_item_history_router)
app.include_router(notifications_router)
app.include_router(work_item_attachments_router)
app.include_router(user_preferences_router)
app.include_router(user_sessions_router)
app.include_router(organization_invitations_router)


@app.get("/")
def read_root():
    return {"message": "DevTrack API is running!"}
