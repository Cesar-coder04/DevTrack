
from fastapi import FastAPI

app = FastAPI(title="DevTrack API")


@app.get("/")
def read_root():
    return {"message": "DevTrack API is running!"}
