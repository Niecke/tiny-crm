from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import auth_backend, fastapi_users
from app.config import settings
from app.db import get_session
from app.logging_config import configure_logging
from app.routers import contacts, documents, projects, tasks, users
from app.schemas.user import UserRead, UserUpdate
from app.storage import check_storage

# Configure JSON logging before anything emits records (and after uvicorn applies
# its own defaults, since uvicorn imports this module on startup).
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Runs some checks when booting the application"""
    await check_storage()
    yield


# FastAPI() creates the ASGI app. title/version show up in auto-generated docs at /docs.
app = FastAPI(title="tinyCRM", version="0.1.0", lifespan=lifespan)

# CORS lets the browser-hosted Flutter app call this API.
# allow_origins=["*"] during local dev; set CORS_ORIGINS env var in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contacts.router)
app.include_router(tasks.router)
app.include_router(documents.router)
app.include_router(projects.router)
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)
# Custom password-change endpoint (must register before fastapi-users users router
# so the more specific /users/me/password route resolves first).
app.include_router(users.router)
# /users/me for profile; no register router — admin created via CLI
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)


@app.get(
    "/health",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "db": "ok",
                        "timestamp": "2026-05-06 15:17:50.366912",
                    }
                }
            }
        },
        503: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "degraded",
                        "db": "error",
                        "timestamp": "2026-05-06 15:17:50.366912",
                    }
                }
            }
        },
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
    ts = str(datetime.now())
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    if not db_ok:
        # Response parameter lets us set the status code without abandoning normal return flow
        response.status_code = 503

    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "timestamp": ts,
    }
