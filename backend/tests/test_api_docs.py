"""The interactive docs and OpenAPI schema are served outside production only.

The app object is built once at import time, so production is checked by
building a throwaway FastAPI app from the same api_docs_urls() the real one uses.
"""

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.config import Environment
from app.main import api_docs_urls, app

_DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.mark.parametrize("path", _DOC_PATHS)
async def test_development_serves_the_docs(path: str) -> None:
    # The test run uses the default environment, i.e. development.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 200


@pytest.mark.parametrize("path", _DOC_PATHS)
async def test_production_does_not_serve_the_docs(path: str) -> None:
    production_app = FastAPI(**api_docs_urls(Environment.production))

    transport = ASGITransport(app=production_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 404


def test_the_schema_can_still_be_exported_in_production() -> None:
    # scripts/export_openapi.py calls app.openapi() directly, not the route.
    production_app = FastAPI(**api_docs_urls(Environment.production))

    assert production_app.openapi()["openapi"].startswith("3.")
