"""One end-to-end-ish check that the app boots and answers.

Deliberately narrow: it exercises the ASGI app in-process, without a database
or object store, so it can run anywhere and still fail loudly if imports,
routing or settings break. The full stack is covered by ci/smoke.sh, which
drives the built containers.
"""

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.version import BUILD_TIMESTAMP, GIT_COMMIT


async def test_version_reports_the_running_build() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "version": GIT_COMMIT,
        "build_timestamp": BUILD_TIMESTAMP,
    }
