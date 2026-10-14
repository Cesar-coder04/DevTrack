from fastapi import FastAPI

from app.api.projects import router as projects_router
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router

app = FastAPI(title="DevTrack API")
app.include_router(auth_router)
app.include_router(users_router)

app.include_router(projects_router)


@app.get("/")
def read_root():
    return {"message": "DevTrack API is running!"}
