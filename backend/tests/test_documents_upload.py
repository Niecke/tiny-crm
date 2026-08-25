"""Unit tests for the upload guards in the documents router.

Both functions are pure enough to test without a database, a bucket or an HTTP
request — which is the point: the size cap has to hold before anything else runs.
"""

import io

import pytest
from fastapi import HTTPException, UploadFile

from app.routers.documents import _MAX_BYTES, _checked_size, _detect_format


def _upload(data: bytes, *, size: int | None) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), size=size, filename="x.txt")


def test_content_type_decides_the_format() -> None:
    assert _detect_format("notes.bin", "application/pdf") == "pdf"
    assert _detect_format("notes.bin", "text/markdown") == "markdown"
    # browsers send this one for .md files
    assert _detect_format("notes.bin", "text/x-markdown") == "markdown"


def test_the_extension_is_the_fallback() -> None:
    assert _detect_format("notes.md", "application/octet-stream") == "markdown"
    assert _detect_format("scan.PDF", "") == "pdf"


def test_unsupported_uploads_are_rejected() -> None:
    assert _detect_format("archive.zip", "application/zip") is None
    assert _detect_format("noextension", "") is None


def test_size_within_the_cap_is_returned() -> None:
    assert _checked_size(_upload(b"x" * 10, size=10)) == 10


def test_oversized_uploads_raise_413_without_being_read() -> None:
    file = _upload(b"", size=_MAX_BYTES + 1)

    with pytest.raises(HTTPException) as raised:
        _checked_size(file)

    assert raised.value.status_code == 413
    # Nothing was consumed: the check never touches the body.
    assert file.file.tell() == 0


def test_a_missing_size_is_measured_and_the_file_rewound() -> None:
    file = _upload(b"abcd", size=None)

    assert _checked_size(file) == 4
    assert file.file.tell() == 0
