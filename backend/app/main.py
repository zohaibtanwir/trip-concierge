from fastapi import FastAPI

from app.routes import plan, trips

app = FastAPI()
app.include_router(trips.router)
app.include_router(plan.router)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
