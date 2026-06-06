from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.db.startup_check import verify_alembic_at_head
from app.rate_limit import limiter
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
    trip_settings,
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

# slowapi wiring for the auth/mcp endpoints (slice 4.1b). The Limiter
# instance lives in app.rate_limit so routes import it without circular
# dependency on this module.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.include_router(trips.router)
app.include_router(trips.internal_router)
app.include_router(plan.router)
app.include_router(refine.router)
app.include_router(regenerate.router)
app.include_router(constraints.router)
app.include_router(trip_settings.router)
app.include_router(alternative.router)
app.include_router(sources.router)
app.include_router(explain.router)
app.include_router(shared.router)
app.include_router(export.router)
app.include_router(auth.router)
app.include_router(auth.internal_router)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
