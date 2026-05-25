from fastapi import FastAPI

from app.routes import trips

app = FastAPI()
app.include_router(trips.router)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
