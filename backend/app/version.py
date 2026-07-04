"""Build/version metadata surfaced by the /version endpoint.

GIT_COMMIT is injected at image build time via the GIT_COMMIT build arg (git
isn't available inside the build container). The build timestamp is written to
a file during the Docker build so it always reflects the actual image, even for
locally built images. Both fall back to "unknown" in a plain dev checkout.
"""

from pathlib import Path

from app.config import settings

# Written by the Dockerfile at the image WORKDIR (/app), next to the app package.
_BUILD_TIMESTAMP_FILE = Path(__file__).resolve().parents[1] / "build_timestamp.txt"


def _read_build_timestamp() -> str:
    try:
        return _BUILD_TIMESTAMP_FILE.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


GIT_COMMIT = settings.git_commit
BUILD_TIMESTAMP = _read_build_timestamp()
