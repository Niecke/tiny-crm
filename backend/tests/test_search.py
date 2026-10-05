"""One search box over every table (#126)."""

from typing import Any, get_args

from httpx2 import AsyncClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
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


async def test_dates_are_sent_as_values_for_the_client_to_format(
    client: AsyncClient, alice: Account
) -> None:
    # 23:59 in Vienna on 5 Oct: already the 5th there, still the 5th in UTC —
    # and the 4th's evening in New York. Which day to show is the reader's.
    due = "2026-10-05T21:59:00Z"
    await create_resource(client, alice, "/tasks/", {"title": "Yak invoice", "due_date": due})
    done = await create_resource(
        client, alice, "/tasks/", {"title": "Yak contract", "due_date": due}
    )
    response = await client.patch(
        f"/tasks/{done['id']}", json={"done": True}, headers=alice.headers
    )
    assert response.status_code == 200, response.text
    await create_resource(
        client, alice, "/interactions/", {"subject": "Yak intro", "occurred_at": PAST}
    )
    await create_resource(
        client, alice, "/projects/", {"name": "Yak rollout", "start_date": "2026-08-01"}
    )

    body = await _search(client, alice, "yak")
    tasks = {hit["title"]: hit for hit in _group(body, "tasks")["items"]}
    assert tasks["Yak invoice"]["subtitle"] is None
    assert tasks["Yak invoice"]["date"] == {"label": "Due", "at": due, "day": None}
    # A finished task's deadline is no longer news.
    assert tasks["Yak contract"]["subtitle"] == "Done"
    assert tasks["Yak contract"]["date"] is None

    interaction = _group(body, "interactions")["items"][0]
    assert interaction["subtitle"] == "Note"
    assert interaction["date"] == {"label": None, "at": PAST, "day": None}

    project = _group(body, "projects")["items"][0]
    assert project["date"] == {"label": "Since", "at": None, "day": "2026-08-01"}


async def test_a_hit_loads_only_what_its_subtitle_shows(
    client: AsyncClient, alice: Account
) -> None:
    org = await create_resource(client, alice, "/organizations/", {"name": "Okapi Labs"})
    contact = await create_resource(
        client, alice, "/contacts/", {"name": "Olive Okapi", "organization_id": org["id"]}
    )
    deal = await create_resource(
        client,
        alice,
        "/deals/",
        {"title": "Okapi relaunch", "contact_id": contact["id"], "organization_id": org["id"]},
    )
    await create_resource(
        client,
        alice,
        "/tasks/",
        {"title": "Okapi follow-up", "contact_id": contact["id"], "deal_id": deal["id"]},
    )

    statements: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        tasks = await _search(client, alice, "okapi", type="tasks")
        deals = await _search(client, alice, "okapi", type="deals")
    finally:
        event.remove(Engine, "before_cursor_execute", record)

    # A task's line names neither its contact nor its deal, so the models'
    # own eager loading — task → deal → contact → organization — stays off.
    assert _titles(tasks, "tasks") == ["Okapi follow-up"]
    # A deal's line names its organization, which comes along in the same
    # statement rather than in one of its own.
    assert _group(deals, "deals")["items"][0]["subtitle"] == "Lead · Okapi Labs"
    reads = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert not [s for s in reads if "FROM contacts" in s or "FROM organizations" in s], reads


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


async def test_the_per_panel_boxes_take_wildcards_literally_too(
    client: AsyncClient, alice: Account
) -> None:
    await create_resource(client, alice, "/contacts/", {"name": "Ten% Club"})
    await create_resource(client, alice, "/contacts/", {"name": "Tennis Club"})
    await create_resource(client, alice, "/contacts/", {"name": "first_name"})
    await create_resource(client, alice, "/contacts/", {"name": "firstXname"})

    for search, found in [("ten%", ["Ten% Club"]), ("first_name", ["first_name"])]:
        response = await client.get("/contacts/", params={"search": search}, headers=alice.headers)
        assert response.status_code == 200, response.text
        assert [c["name"] for c in response.json()["items"]] == found


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
    response = await client.get("/search/", params={"q": "xx", "skip": 5}, headers=alice.headers)
    assert response.status_code == 422


async def test_a_blank_query_is_refused(client: AsyncClient, alice: Account) -> None:
    for q in ["", "   "]:
        response = await client.get("/search/", params={"q": q}, headers=alice.headers)
        assert response.status_code == 422


async def test_a_single_character_is_refused(client: AsyncClient, alice: Account) -> None:
    # Padding does not make it two.
    for q in ["a", " a ", "a  "]:
        response = await client.get("/search/", params={"q": q}, headers=alice.headers)
        assert response.status_code == 422, q
    assert (await _search(client, alice, "ab"))["q"] == "ab"


async def test_a_nul_character_is_refused_not_sent_to_the_database(
    client: AsyncClient, alice: Account
) -> None:
    # Postgres text cannot hold one; unchecked, the driver's refusal was a 500.
    for q in ["\x00\x00", "anna\x00", "an\x00na acme"]:
        response = await client.get("/search/", params={"q": q}, headers=alice.headers)
        assert response.status_code == 422, repr(q)


async def test_search_needs_a_login(client: AsyncClient) -> None:
    response = await client.get("/search/", params={"q": "xx"})
    assert response.status_code == 401


async def test_nobody_finds_another_tenants_rows(
    client: AsyncClient, alice: Account, bob: Account
) -> None:
    await create_resource(client, alice, "/contacts/", {"name": "Secret Client"})
    await create_resource(client, alice, "/captures/", {"raw": "secret lead"})

    body = await _search(client, bob, "secret")
    assert all(g["total"] == 0 and g["items"] == [] for g in body["groups"])
