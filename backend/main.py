from fastapi import FastAPI

from app.api.projects import router as projects_router

app = FastAPI(title="DevTrack API")

app.include_router(projects_router)


@app.get("/")
def read_root():
    return {"message": "DevTrack API is running!"}
