"""One search box over every table (#126)."""

from typing import Any, get_args

from httpx2 import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.document import Document
from app.models.search import SEARCHABLES
from app.schemas.search import SearchType
from tests.conftest import Account, create_resource

PAST = "2026-09-01T10:00:00Z"


async def _search(client: AsyncClient, account: Account, q: str, **params: Any) -> dict[str, Any]:
    response = await client.get("/search/", params={"q": q, **params}, headers=account.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _group(body: dict[str, Any], type_: str) -> dict[str, Any]:
    group: dict[str, Any] = next(g for g in body["groups"] if g["type"] == type_)
    return group


def _titles(body: dict[str, Any], type_: str) -> list[str]:
    return [hit["title"] for hit in _group(body, type_)["items"]]


def test_the_schema_names_every_searchable_table() -> None:
    assert [s.key for s in SEARCHABLES] == list(get_args(SearchType))


async def test_a_contact_is_found_by_email_phone_and_notes(
    client: AsyncClient, alice: Account
) -> None:
    await create_resource(
        client,
        alice,
        "/contacts/",
        {
            "name": "Jane Doe",
            "email": "jane@example.org",
            "phone": "+43 664 123 45 67",
            "notes": "Met at the Vienna Kubernetes meetup",
            "tags": ["speaker"],
        },
    )

    by_email = _group(await _search(client, alice, "jane@exam"), "contacts")
    assert by_email["total"] == 1
    assert by_email["items"][0]["match"] == {"field": "Email", "excerpt": "jane@example.org"}

    # However the number was typed in, the digits alone find it.
    by_phone = _group(await _search(client, alice, "6641234"), "contacts")
    assert by_phone["items"][0]["title"] == "Jane Doe"
    assert by_phone["items"][0]["match"] == {"field": "Phone", "excerpt": "+43 664 123 45 67"}

    by_note = _group(await _search(client, alice, "kubernetes"), "contacts")
    assert by_note["items"][0]["match"]["field"] == "Notes"
    assert "Kubernetes" in by_note["items"][0]["match"]["excerpt"]

    assert _titles(await _search(client, alice, "speaker"), "contacts") == ["Jane Doe"]

    # A hit by its own name needs no explaining.
    by_name = _group(await _search(client, alice, "jane doe"), "contacts")
    assert by_name["items"][0]["match"] is None


async def test_every_table_answers_one_query(
    client: AsyncClient,
    alice: Account,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = await create_resource(client, alice, "/organizations/", {"name": "Zebra Labs"})
    await create_resource(
        client, alice, "/contacts/", {"name": "Zebra Person", "organization_id": org["id"]}
    )
    await create_resource(client, alice, "/deals/", {"title": "Zebra relaunch"})
    await create_resource(client, alice, "/tasks/", {"title": "Call zebra"})
    await create_resource(
        client, alice, "/interactions/", {"subject": "Zebra intro", "occurred_at": PAST}
    )
    await create_resource(
        client, alice, "/projects/", {"name": "Zebra rollout", "start_date": "2026-08-01"}
    )
    await create_resource(
        client,
        alice,
        "/watches/",
        {
            "name": "Zebra careers",
            "url": "https://zebra.example/jobs",
            "kind": "careers_page",
            "recurrence_rule": "weekly",
        },
    )
    await create_resource(client, alice, "/captures/", {"raw": "zebra founder, ask about Q4"})
    async with session_factory() as session:
        session.add(
            Document(
                user_id=alice.id,
                title="Zebra contract",
                format="pdf",
                size=1,
                storage_key="k",
            )
        )
        await session.commit()

    body = await _search(client, alice, "zebra")
    assert body["q"] == "zebra"
    assert [g["type"] for g in body["groups"]] == list(get_args(SearchType))
    for group in body["groups"]:
        assert group["total"] == 1, group
        assert len(group["items"]) == 1
    contact = _group(body, "contacts")["items"][0]
    assert contact["subtitle"] == "Zebra Labs"
    assert _group(body, "captures")["items"][0]["subtitle"] == "Waiting"


async def test_captures_are_found_by_raw_text_whatever_their_status(
    client: AsyncClient, alice: Account
) -> None:
    capture = await create_resource(
        client, alice, "/captures/", {"raw": "https://www.linkedin.com/in/jane-doe-4b21"}
    )
    dismissed = await client.post(f"/captures/{capture['id']}/dismiss", headers=alice.headers)
    assert dismissed.status_code == 200

    group = _group(await _search(client, alice, "4b21"), "captures")
    assert group["total"] == 1
    hit = group["items"][0]
    # Titled by the guessed name, found by the link it was parked as.
    assert hit["title"] == "Jane Doe"
    assert hit["subtitle"] == "Dismissed"
    assert hit["match"]["field"] == "Captured"


async def test_every_term_has_to_match(client: AsyncClient, alice: Account) -> None:
    await create_resource(client, alice, "/contacts/", {"name": "Anna", "notes": "works at ACME"})
    await create_resource(client, alice, "/contacts/", {"name": "Anna", "notes": "Globex"})
    await create_resource(client, alice, "/contacts/", {"name": "Bert", "notes": "ACME too"})

    group = _group(await _search(client, alice, "anna acme"), "contacts")
    assert group["total"] == 1
    assert group["items"][0]["match"]["field"] == "Notes"


async def test_titles_starting_with_the_query_rank_first(
    client: AsyncClient, alice: Account
) -> None:
    for name in ["Johanna Berg", "Zed", "Anna Berger"]:
        notes = "anna's colleague" if name == "Zed" else None
        await create_resource(client, alice, "/contacts/", {"name": name, "notes": notes})

    assert _titles(await _search(client, alice, "anna"), "contacts") == [
        "Anna Berger",
        "Johanna Berg",
        "Zed",
    ]


async def test_like_wildcards_are_taken_literally(client: AsyncClient, alice: Account) -> None:
    await create_resource(client, alice, "/tasks/", {"title": "Raise rate by 10%"})
    await create_resource(client, alice, "/tasks/", {"title": "Raise rate by 100 EUR"})
    await create_resource(client, alice, "/tasks/", {"title": "rename first_name"})
    await create_resource(client, alice, "/tasks/", {"title": "rename firstXname"})

    assert _titles(await _search(client, alice, "10%"), "tasks") == ["Raise rate by 10%"]
    assert _titles(await _search(client, alice, "first_name"), "tasks") == ["rename first_name"]


async def test_one_type_pages_through_all_of_its_hits(client: AsyncClient, alice: Account) -> None:
    for index in range(7):
        await create_resource(client, alice, "/organizations/", {"name": f"Company {index}"})

    overview = await _search(client, alice, "company")
    assert _group(overview, "organizations")["total"] == 7
    assert len(_group(overview, "organizations")["items"]) == 5

    second = await _search(client, alice, "company", type="organizations", skip=5, limit=5)
    assert [g["type"] for g in second["groups"]] == ["organizations"]
    assert _titles(second, "organizations") == ["Company 5", "Company 6"]
    assert second["groups"][0]["total"] == 7


async def test_paging_needs_a_type(client: AsyncClient, alice: Account) -> None:
    response = await client.get("/search/", params={"q": "x", "skip": 5}, headers=alice.headers)
    assert response.status_code == 422


async def test_a_blank_query_is_refused(client: AsyncClient, alice: Account) -> None:
    for q in ["", "   "]:
        response = await client.get("/search/", params={"q": q}, headers=alice.headers)
        assert response.status_code == 422


async def test_search_needs_a_login(client: AsyncClient) -> None:
    response = await client.get("/search/", params={"q": "x"})
    assert response.status_code == 401


async def test_nobody_finds_another_tenants_rows(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    await create_resource(client, alice, "/contacts/", {"name": "Secret Client"})
    await create_resource(client, alice, "/captures/", {"raw": "secret lead"})

    body = await _search(client, bob, "secret")
    assert all(g["total"] == 0 and g["items"] == [] for g in body["groups"])
