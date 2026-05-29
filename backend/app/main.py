from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.startup_check import verify_alembic_at_head
from app.routes import (
    alternative,
    auth,
    constraints,
    explain,
    export,
    plan,
    refine,
    regenerate,
    shared,
    sources,
    trips,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    # Runs at uvicorn startup AND at TestClient context entry. Raises and
    # aborts startup if the DB is behind the code's expected schema. See
    # app/db/startup_check.py for the why.
    verify_alembic_at_head()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(trips.router)
app.include_router(plan.router)
app.include_router(refine.router)
app.include_router(regenerate.router)
app.include_router(constraints.router)
app.include_router(alternative.router)
app.include_router(sources.router)
app.include_router(explain.router)
app.include_router(shared.router)
app.include_router(export.router)
app.include_router(auth.router)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
