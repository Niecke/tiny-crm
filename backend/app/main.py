from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session

# FastAPI() creates the ASGI app. title/version show up in auto-generated docs at /docs.
app = FastAPI(title="tinyCRM", version="0.1.0")

# CORS lets the browser-hosted Flutter app call this API.
# allow_origins=["*"] during local dev; set CORS_ORIGINS env var in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    responses={
        200: {"content": {"application/json": {"example": {"status": "ok", "db": "ok"}}}},
        503: {"content": {"application/json": {"example": {"status": "degraded", "db": "error"}}}},
    },
)
async def health(
    response: Response,
    # Depends() injects get_session — FastAPI opens a session, passes it here, closes it after
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """
    Returns service status including database connectivity.

    Returns 503 when the database is unreachable.
    Suitable for load balancer health checks.
    """
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    if not db_ok:
        # Response parameter lets us set the status code without abandoning normal return flow
        response.status_code = 503

    return {"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "error"}


@app.get("/ping")
async def ping() -> dict[str, str]:
    """
    Just a test endpoint for the flutter frontend.
    """
    return {"result": "pong"}
