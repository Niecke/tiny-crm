"""Business card scanning (#262): photos in, a draft out, the corrected draft filed.

The model is replaced by a fake reader — what is under test is everything around
it: the upload guards, turning a reading into drafts, finding the company that
is already on file, and filing the card without leaving half of it behind.
"""

import json
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest
from httpx2 import AsyncClient

from app.business_cards import (
    CardImage,
    CardRead,
    CardReadError,
    CardReading,
    CardReadUsage,
    ClaudeCardReader,
    get_card_reader,
    sniff_image_type,
)
from app.config import settings
from app.main import app
from app.routers.business_cards import company_domain, normalise_domain, to_drafts
from tests.conftest import Account, create_resource

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

READING = CardReading(
    name="Ada Lovelace",
    job_title="Head of Engineering",
    email="ada@acme.example",
    phone="+43 660 1234567",
    website="https://www.acme.example/",
    street="Hauptstraße 1",
    postal_code="1010",
    city="Wien",
    country="at",
    organization_name="ACME GmbH",
    organization_email="office@acme.example",
    organization_phone="+43 1 234 5678",
)


USAGE = CardReadUsage(model="claude-opus-5-5", input_tokens=1234, output_tokens=210)


class FakeReader:
    def __init__(self, reading: CardReading = READING) -> None:
        self.reading = reading
        self.calls: list[list[CardImage]] = []
        self.fail: str | None = None

    async def read(self, images: list[CardImage]) -> CardRead:
        self.calls.append(images)
        if self.fail:
            raise CardReadError(self.fail)
        return CardRead(self.reading, USAGE)


@pytest.fixture
def reader(client: AsyncClient) -> Iterator[FakeReader]:
    fake = FakeReader()
    app.dependency_overrides[get_card_reader] = lambda: fake
    yield fake


async def _scan(client: AsyncClient, account: Account, **files: bytes) -> Any:
    return await client.post(
        "/business-cards/scan",
        files={side: (f"{side}.jpg", data, "image/jpeg") for side, data in files.items()},
        headers=account.headers,
    )


# --- Scanning ----------------------------------------------------------------


async def test_a_scan_returns_a_draft_of_the_person_and_the_company(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    response = await _scan(client, alice, front=JPEG, back=PNG)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["contact"]["name"] == "Ada Lovelace"
    assert body["contact"]["country"] == "AT"
    assert body["organization"] == {
        "name": "ACME GmbH",
        "domain": "acme.example",
        "email": "office@acme.example",
        "phone": "+43 1 234 5678",
        "address": "Hauptstraße 1, 1010 Wien, AT",
    }
    assert body["match"] is None
    # What the read cost, for checking against the price list.
    assert body["usage"] == {
        "model": "claude-opus-5-5",
        "input_tokens": 1234,
        "output_tokens": 210,
    }
    # Both sides went to the reader, front first, each as what it really is.
    assert [image.media_type for image in reader.calls[0]] == ["image/jpeg", "image/png"]


async def test_the_back_is_optional(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    response = await _scan(client, alice, front=JPEG)
    assert response.status_code == 200, response.text
    assert len(reader.calls[0]) == 1


async def test_a_scan_writes_nothing(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    await _scan(client, alice, front=JPEG)
    contacts = await client.get("/contacts/", headers=alice.headers)
    organizations = await client.get("/organizations/", headers=alice.headers)
    assert contacts.json()["total"] == 0
    assert organizations.json()["total"] == 0


@pytest.mark.parametrize(
    "stored",
    [
        "acme.example",
        "www.acme.example",
        "https://www.ACME.example",
        "https://acme.example/team",
        "https://acme.example?ref=card",
        "acme.example#contact",
        "http://acme.example:8080/",
        " Acme.Example ",
    ],
)
async def test_the_company_on_file_is_found_by_its_domain(
    client: AsyncClient, alice: Account, reader: FakeReader, stored: str
) -> None:
    # Stored however it was typed and under a different name: the domain still
    # says it is the same company.
    org = await create_resource(
        client, alice, "/organizations/", {"name": "Acme", "domain": stored}
    )
    body = (await _scan(client, alice, front=JPEG)).json()
    assert body["match"] == {"id": org["id"], "name": "Acme", "matched_on": "domain"}


@pytest.mark.parametrize("stored", ["notacme.example", "acme.example.org", "shop.acme.example"])
async def test_a_different_domain_is_not_a_match(
    client: AsyncClient, alice: Account, reader: FakeReader, stored: str
) -> None:
    await create_resource(client, alice, "/organizations/", {"name": "Other", "domain": stored})
    body = (await _scan(client, alice, front=JPEG)).json()
    assert body["match"] is None


async def test_the_company_on_file_is_found_by_its_name(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    org = await create_resource(client, alice, "/organizations/", {"name": "acme gmbh"})
    body = (await _scan(client, alice, front=JPEG)).json()
    assert body["match"] == {"id": org["id"], "name": "acme gmbh", "matched_on": "name"}


async def test_another_users_company_is_never_a_match(
    client: AsyncClient, alice: Account, bob: Account, reader: FakeReader
) -> None:
    await create_resource(
        client, bob, "/organizations/", {"name": "ACME GmbH", "domain": "acme.example"}
    )
    body = (await _scan(client, alice, front=JPEG)).json()
    assert body["match"] is None


async def test_an_archived_company_is_not_a_match(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    org = await create_resource(
        client, alice, "/organizations/", {"name": "ACME GmbH", "domain": "acme.example"}
    )
    await client.post(f"/organizations/{org['id']}/archive", headers=alice.headers)
    body = (await _scan(client, alice, front=JPEG)).json()
    assert body["match"] is None


async def test_a_card_with_no_company_has_no_organization_draft(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    reader.reading = CardReading(name="Ada Lovelace", email="ada@gmail.com")
    body = (await _scan(client, alice, front=JPEG)).json()
    assert body["organization"] is None
    assert body["match"] is None


async def test_photos_with_nothing_readable_are_refused(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    reader.reading = CardReading()
    response = await _scan(client, alice, front=JPEG)
    assert response.status_code == 422


async def test_a_file_that_is_not_an_image_is_refused(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    response = await _scan(client, alice, front=b"%PDF-1.7 not a photo")
    assert response.status_code == 415
    assert reader.calls == []


async def test_a_photo_over_5_mb_is_refused(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    response = await _scan(client, alice, front=JPEG, back=JPEG + b"\x00" * (5 * 1024 * 1024))
    assert response.status_code == 413
    assert "back" in response.json()["detail"]
    assert reader.calls == []


async def test_a_failed_read_is_a_502_with_the_readers_message(
    client: AsyncClient, alice: Account, reader: FakeReader
) -> None:
    reader.fail = "The card reader is busy — try again in a minute."
    response = await _scan(client, alice, front=JPEG)
    assert response.status_code == 502
    assert response.json()["detail"] == reader.fail


async def test_without_an_api_key_scanning_is_unavailable(
    client: AsyncClient, alice: Account
) -> None:
    app.dependency_overrides[get_card_reader] = lambda: None
    response = await _scan(client, alice, front=JPEG)
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


async def test_scanning_needs_a_login(client: AsyncClient, reader: FakeReader) -> None:
    response = await client.post(
        "/business-cards/scan", files={"front": ("front.jpg", JPEG, "image/jpeg")}
    )
    assert response.status_code == 401
    assert reader.calls == []


# --- Importing ---------------------------------------------------------------


async def test_import_files_a_new_company_and_the_contact_under_it(
    client: AsyncClient, alice: Account
) -> None:
    response = await client.post(
        "/business-cards/import",
        json={
            "contact": {"name": "Ada Lovelace", "email": "ada@acme.example", "country": "at"},
            "organization": {"name": "ACME GmbH", "domain": "acme.example"},
        },
        headers=alice.headers,
    )
    assert response.status_code == 201, response.text
    contact = response.json()
    assert contact["organization_name"] == "ACME GmbH"
    assert contact["country"] == "AT"

    org = await client.get(f"/organizations/{contact['organization_id']}", headers=alice.headers)
    assert org.json()["contact_count"] == 1


async def test_import_files_the_contact_under_a_company_on_file(
    client: AsyncClient, alice: Account
) -> None:
    org = await create_resource(client, alice, "/organizations/", {"name": "ACME GmbH"})
    response = await client.post(
        "/business-cards/import",
        json={"contact": {"name": "Ada Lovelace", "organization_id": org["id"]}},
        headers=alice.headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["organization_id"] == org["id"]
    organizations = await client.get("/organizations/", headers=alice.headers)
    assert organizations.json()["total"] == 1


async def test_import_refuses_two_answers_to_which_company(
    client: AsyncClient, alice: Account
) -> None:
    org = await create_resource(client, alice, "/organizations/", {"name": "ACME GmbH"})
    response = await client.post(
        "/business-cards/import",
        json={
            "contact": {"name": "Ada Lovelace", "organization_id": org["id"]},
            "organization": {"name": "Another GmbH"},
        },
        headers=alice.headers,
    )
    assert response.status_code == 422


async def test_import_cannot_file_under_another_users_company(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    org = await create_resource(client, bob, "/organizations/", {"name": "Bob's GmbH"})
    response = await client.post(
        "/business-cards/import",
        json={"contact": {"name": "Ada Lovelace", "organization_id": org["id"]}},
        headers=alice.headers,
    )
    assert response.status_code == 404


async def test_a_refused_import_leaves_no_company_behind(
    client: AsyncClient, alice: Account
) -> None:
    # Half a rate is refused — and the new company must not be filed without
    # the person it was created for.
    response = await client.post(
        "/business-cards/import",
        json={
            "contact": {"name": "Ada Lovelace", "known_day_rate": "800"},
            "organization": {"name": "ACME GmbH"},
        },
        headers=alice.headers,
    )
    assert response.status_code == 422
    organizations = await client.get("/organizations/", headers=alice.headers)
    assert organizations.json()["total"] == 0


async def test_import_needs_a_login(client: AsyncClient) -> None:
    response = await client.post(
        "/business-cards/import", json={"contact": {"name": "Ada Lovelace"}}
    )
    assert response.status_code == 401


# --- Pure helpers ------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (b"GIF89a" + b"\x00" * 8, "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"%PDF-1.7", None),
        (b"", None),
    ],
)
def test_image_types_are_recognised_by_their_bytes(data: bytes, expected: str | None) -> None:
    assert sniff_image_type(data) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("acme.example", "acme.example"),
        ("https://www.Acme.example/team", "acme.example"),
        ("www.acme.example", "acme.example"),
        ("not a domain", None),
        ("", None),
        (None, None),
    ],
)
def test_domains_are_normalised(value: str | None, expected: str | None) -> None:
    assert normalise_domain(value) == expected


def test_the_company_domain_falls_back_to_the_email() -> None:
    assert company_domain(CardReading(email="ada@acme.example")) == "acme.example"


def test_a_mailbox_providers_domain_is_not_the_companys() -> None:
    assert company_domain(CardReading(email="ada@gmail.com")) is None


def test_a_country_that_is_not_a_code_is_dropped() -> None:
    contact, _ = to_drafts(CardReading(name="Ada", country="Austria"))
    assert contact.country is None


# --- The Claude reader -------------------------------------------------------


def _claude(handler: Any) -> ClaudeCardReader:
    return ClaudeCardReader(
        "sk-test",
        "claude-opus-5-5",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )


def _message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1500, "output_tokens": 180},
    }


async def test_the_claude_reader_sends_both_sides_and_parses_the_answer() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        assert request.headers["x-api-key"] == "sk-test"
        return httpx2.Response(200, json=_message(READING.model_dump_json()))

    read = await _claude(handler).read([CardImage(JPEG, "image/jpeg"), CardImage(PNG, "image/png")])
    assert read.reading == READING
    assert read.usage == CardReadUsage(
        model="claude-opus-5-5", input_tokens=1500, output_tokens=180
    )

    content = sent[0]["messages"][0]["content"]
    images = [block for block in content if block["type"] == "image"]
    assert [image["source"]["media_type"] for image in images] == ["image/jpeg", "image/png"]
    assert sent[0]["model"] == "claude-opus-5-5"


@pytest.mark.parametrize(
    ("text", "stop_reason"),
    [
        # A refusal carries no JSON, so the SDK's parser fails before returning.
        ("", "refusal"),
        ('{"name": "Ada', "max_tokens"),
        (READING.model_dump_json(), "refusal"),
    ],
)
async def test_the_claude_reader_reports_an_answer_it_cannot_use(
    text: str, stop_reason: str
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_message(text, stop_reason=stop_reason))

    with pytest.raises(CardReadError):
        await _claude(handler).read([CardImage(JPEG, "image/jpeg")])


async def test_the_claude_reader_reports_an_api_error_without_its_body() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "x"}}
        )

    with pytest.raises(CardReadError, match="refused"):
        await _claude(handler).read([CardImage(JPEG, "image/jpeg")])


async def test_the_readers_client_is_closed_after_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    dependency = get_card_reader()
    reader = await anext(dependency)
    assert isinstance(reader, ClaudeCardReader)
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)
    assert reader._client.is_closed()


async def test_without_a_key_there_is_no_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    assert await anext(get_card_reader()) is None


@pytest.mark.parametrize(
    ("response", "shown", "logged"),
    [
        (httpx2.ReadTimeout("slow"), "took too long", "timed out"),
        (httpx2.ConnectError("refused"), "Could not reach", "could not connect"),
        (
            httpx2.Response(
                429,
                json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}},
            ),
            "busy",
            "HTTP 429 rate_limit_error: slow",
        ),
        (
            httpx2.Response(
                400,
                json={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Your credit balance is too low",
                    },
                },
            ),
            "refused",
            "HTTP 400 invalid_request_error: Your credit balance is too low",
        ),
    ],
)
async def test_every_failed_read_is_logged(
    caplog: pytest.LogCaptureFixture,
    response: httpx2.Response | Exception,
    shown: str,
    logged: str,
) -> None:
    # The SDK's own retry line used to be the only trace of a timeout, a
    # connection error or a rate limit.
    def handler(request: httpx2.Request) -> httpx2.Response:
        if isinstance(response, Exception):
            raise response
        return response

    with pytest.raises(CardReadError, match=shown):
        await _claude(handler).read([CardImage(JPEG, "image/jpeg")])
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert any(logged in message for message in errors), errors
