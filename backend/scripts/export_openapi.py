#!/usr/bin/env python3
"""Write the API's OpenAPI schema as JSON, without starting a server.

The React client generates its types from this file (FRONTEND.md, "API
client"). Importing the app is enough: FastAPI builds the schema from the
routers and Pydantic models, and nothing here touches the database or S3.

Usage:
    python scripts/export_openapi.py > ../frontend-next/openapi.json
"""

import json
import sys
from pathlib import Path

# Run directly (`python scripts/export_openapi.py`) and Python puts this
# script's directory on sys.path, not the backend root -- so `app` wouldn't
# import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402


def main() -> None:
    # Indented and in FastAPI's own order, so a backend change shows up in a
    # pull request as a readable diff of this file.
    json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
