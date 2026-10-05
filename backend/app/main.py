import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TypedDict

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import fastapi_users
from app.config import Environment, settings
from app.db import get_session
from app.logging_config import configure_logging
from app.ratelimit import count_failed_logins
from app.routers import (
    auth,
    briefing,
    captures,
    contacts,
    deals,
    documents,
    interactions,
    organizations,
    projects,
    search,
    tasks,
    users,
    watches,
)
from app.schemas.user import UserRead
from app.storage import check_storage
from app.version import APP_VERSION, BUILD_TIMESTAMP, GIT_COMMIT

# Configure JSON logging before anything emits records (and after uvicorn applies
# its own defaults, since uvicorn imports this module on startup).
configure_logging()

logger = logging.getLogger(__name__)


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when a production instance still runs on dev defaults."""


def check_secure_defaults() -> None:
    """Warn about unsafe built-in defaults; refuse to start on them in production.

    Raising here aborts uvicorn's startup, which exits with code 3 — so a
    misconfigured production container fails immediately and visibly instead of
    serving traffic with a known secret or a wildcard CORS policy.
    """
    problems = settings.insecure_defaults()
    if not problems:
        return

    if settings.environment is Environment.production:
        for problem in problems:
            logger.error("Insecure configuration: %s", problem)
        raise InsecureConfigurationError(
            f"Refusing to start with ENVIRONMENT=production and "
            f"{len(problems)} insecure default(s); see the errors above."
        )

    for problem in problems:
        logger.warning("Insecure default (allowed outside production): %s", problem)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Runs some checks when booting the application"""
    check_secure_defaults()
    await check_storage()
    yield


class ApiDocsUrls(TypedDict):
    docs_url: str | None
    redoc_url: str | None
    openapi_url: str | None


def api_docs_urls(environment: Environment) -> ApiDocsUrls:
    """Where FastAPI serves the interactive docs and the OpenAPI schema.

    Production serves none of them: every endpoint is authenticated anyway, but
    nobody besides the operator needs the full API surface, so there is no reason
    to hand it out unauthenticated. Development keeps them. app.openapi() still
    builds the schema either way, so scripts/export_openapi.py is unaffected.
    """
    if environment is Environment.production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


# FastAPI() creates the ASGI app. title/version show up in auto-generated docs at /docs
# (served outside production only, see api_docs_urls()).
app = FastAPI(
    title="tinyCRM",
    version="0.1.0",
    lifespan=lifespan,
    **api_docs_urls(settings.environment),
)

# CORS lets the browser-hosted frontend call this API.
# allow_origins=["*"] during local dev; set CORS_ORIGINS env var in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Records failed logins for the throttle below. Registered as middleware rather
# than a dependency because only the response reveals whether the credentials
# were accepted.
app.middleware("http")(count_failed_logins)

app.include_router(contacts.router)
app.include_router(captures.router)
app.include_router(organizations.router)
app.include_router(deals.router)
app.include_router(tasks.router)
app.include_router(documents.router)
app.include_router(projects.router)
app.include_router(interactions.router)
app.include_router(watches.router)
app.include_router(search.router)
app.include_router(briefing.router)
# /auth/jwt/login, /refresh and /logout. The throttle covers logout as well as
# login. That is deliberate: both are the credential surface, and the budget is
# generous enough that no real session hits it.
app.include_router(auth.router)
# /auth/forgot-password + /auth/reset-password. forgot-password answers 202 whether
# or not the address exists, so it does not reveal which accounts do.
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)
# /auth/request-verify-token + /auth/verify
app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)
# GET /users/me and POST /users/me/password. Not fastapi-users' users router: its
# PATCH /users/me set a new password without the old one and changed the email
# address — which, with password reset, redirected every reset link (#150).
app.include_router(users.router)


@app.get(
    "/version",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "version": "94170aa",
                        "app_version": "v0.1.0-94170aa",
                        "build_timestamp": "2026-07-04T19:33:00Z",
                    }
                }
            }
        }
    },
)
async def version() -> dict[str, str]:
    """Returns the running build's git commit, product version and image build timestamp."""
    return {
        "version": GIT_COMMIT,
        "app_version": APP_VERSION,
        "build_timestamp": BUILD_TIMESTAMP,
    }


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
