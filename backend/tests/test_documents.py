"""Documents through the API, with the object store faked in memory.

Only the S3 calls are replaced — routing, ownership, the size cap and the
database row all run for real. The genuine S3 round-trip is ci/smoke.sh.
"""

from collections.abc import AsyncIterator, Iterator
from typing import BinaryIO

import pytest
from httpx2 import AsyncClient

from app.routers import documents
from tests.conftest import Account, erase


@pytest.fixture
def object_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, bytes]]:
    store: dict[str, bytes] = {}

    async def put_object(key: str, data: bytes, content_type: str) -> None:
        store[key] = bytes(data)

    async def put_object_stream(key: str, fileobj: BinaryIO, content_type: str) -> None:
        fileobj.seek(0)
        store[key] = fileobj.read()

    async def get_object_stream(key: str) -> AsyncIterator[bytes]:
        yield store[key]

    async def delete_object(key: str) -> None:
        store.pop(key, None)

    monkeypatch.setattr(documents, "put_object", put_object)
    monkeypatch.setattr(documents, "put_object_stream", put_object_stream)
    monkeypatch.setattr(documents, "get_object_stream", get_object_stream)
    monkeypatch.setattr(documents, "delete_object", delete_object)
    yield store


async def _upload(
    client: AsyncClient,
    account: Account,
    *,
    title: str = "Notes",
    filename: str = "notes.txt",
    content: bytes = b"hello from the test suite\n",
    content_type: str = "text/plain",
) -> dict[str, object]:
    response = await client.post(
        "/documents/",
        data={"title": title, "tags": "[]"},
        files={"file": (filename, content, content_type)},
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    uploaded: dict[str, object] = response.json()
    return uploaded


async def test_a_document_round_trips_through_the_store(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    content = b"hello from the test suite\n"
    document = await _upload(client, alice, content=content)

    assert document["format"] == "txt"
    assert document["size"] == len(content)
    assert document["has_preview"] is False
    assert list(object_store.values()) == [content]

    downloaded = await client.get(f"/documents/{document['id']}/content", headers=alice.headers)
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert "attachment" in downloaded.headers["content-disposition"]


async def test_content_disposition_sanitizes_control_chars_and_supports_utf8(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    # Title with newlines, quotes, backslashes, and German umlauts
    title = 'Vertrag\r\n"Entwurf"\\2026 Überweisung'
    document = await _upload(client, alice, title=title)

    downloaded = await client.get(f"/documents/{document['id']}/content", headers=alice.headers)
    assert downloaded.status_code == 200

    disposition = downloaded.headers["content-disposition"]
    # No raw CR or LF in headers
    assert "\r" not in disposition
    assert "\n" not in disposition
    # Check ASCII fallback excludes quotes, backslashes and control chars
    assert 'filename="VertragEntwurf2026 berweisung.txt"' in disposition
    # Check UTF-8 RFC 5987 encoding
    assert (
        "filename*=UTF-8''Vertrag%0D%0A%22Entwurf%22%5C2026%20%C3%9Cberweisung.txt" in disposition
    )


async def test_content_disposition_fallback_for_purely_non_ascii_title(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    document = await _upload(client, alice, title="🚀✨")

    downloaded = await client.get(f"/documents/{document['id']}/content", headers=alice.headers)
    assert downloaded.status_code == 200

    disposition = downloaded.headers["content-disposition"]
    assert 'filename="document.txt"' in disposition
    assert "filename*=UTF-8''%F0%9F%9A%80%E2%9C%A8.txt" in disposition


async def test_replacing_the_content_updates_the_row_and_the_store(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    document = await _upload(client, alice)
    replacement = b"# Rewritten\n"

    response = await client.put(
        f"/documents/{document['id']}/content",
        files={"file": ("notes.md", replacement, "text/markdown")},
        headers=alice.headers,
    )

    assert response.status_code == 200
    assert response.json()["format"] == "markdown"
    assert response.json()["size"] == len(replacement)
    assert list(object_store.values()) == [replacement]


async def test_metadata_can_be_edited_without_touching_the_file(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    document = await _upload(client, alice)

    response = await client.patch(
        f"/documents/{document['id']}",
        json={"title": "Renamed", "tags": ["contract"]},
        headers=alice.headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    assert response.json()["tags"] == ["contract"]
    assert len(object_store) == 1


async def test_deleting_a_document_removes_the_object(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    document = await _upload(client, alice)

    response = await erase(client, alice, f"/documents/{document['id']}")

    assert response.status_code == 204
    assert object_store == {}
    assert (
        await client.get(f"/documents/{document['id']}", headers=alice.headers)
    ).status_code == 404


async def test_an_unsupported_file_type_is_refused(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    response = await client.post(
        "/documents/",
        data={"title": "Archive", "tags": "[]"},
        files={"file": ("backup.zip", b"PK\x03\x04", "application/zip")},
        headers=alice.headers,
    )

    assert response.status_code == 422
    assert object_store == {}


async def test_a_missing_preview_is_a_404(
    client: AsyncClient, alice: Account, object_store: dict[str, bytes]
) -> None:
    document = await _upload(client, alice)

    response = await client.get(f"/documents/{document['id']}/preview", headers=alice.headers)

    assert response.status_code == 404
