"""The size cap every upload endpoint applies, in one place.

Documents, the lead CSV and the vCard import each take a file and each have a
limit. Three copies of the same check is two that will be forgotten the next
time it changes.
"""

import os

from fastapi import HTTPException, UploadFile


def checked_size(file: UploadFile, max_bytes: int) -> int:
    """Size of the upload, checked before any of it is pulled into memory.

    Starlette has already received the body — spooling it to a temp file past
    1 MB — and recorded its length, so this reads a counter rather than the
    file. Everything downstream streams, so an oversized upload is rejected
    without ever becoming a bytes object here."""
    size = file.size
    if size is None:  # no Content-Length from the client
        size = file.file.seek(0, os.SEEK_END)
        file.file.seek(0)
    if size > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"File exceeds {max_bytes // (1024 * 1024)} MB limit"
        )
    return size
