"""The agent API (#320): token authentication and the five read-only routes.

Token management is in test_api_tokens.py. Rows are built directly: the routes
under test only read, and some of what they must leave out (archived rows,
other tenants') is easiest to say as data.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx2 import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.api_tokens import ApiToken
from app.auth.users import User
from app.main import app
from app.models import Contact, Deal, Interaction, Organization, Task
from app.routers.briefing import current_time
from tests.conftest import Account

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 9, 4, 7, 0, tzinfo=BERLIN)
TOKENS = "/users/me/api-tokens/"


async def token_for(client: AsyncClient, account: Account) -> dict[str, str]:
    """A fresh API token for `account`, as a Bearer header."""
    response = await client.post(TOKENS, json={"name": "agent"}, headers=account.headers)
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
async def alice_token(client: AsyncClient, alice: Account) -> dict[str, str]:
    return await token_for(client, alice)


@pytest.fixture
async def bob_token(client: AsyncClient, bob: Account) -> dict[str, str]:
    return await token_for(client, bob)


async def seed(session_factory: async_sessionmaker[AsyncSession], *rows: Any) -> None:
    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()


def deal(account: Account, title: str, stage: str = "lead", **fields: Any) -> Deal:
    fields.setdefault("stage_changed_at", NOW - timedelta(days=3))
    return Deal(user_id=account.id, title=title, stage=stage, **fields)


# --- Authentication ----------------------------------------------------------

ROUTES = [
    "/v1/agent/search?q=anna",
    "/v1/agent/contacts/00000000-0000-0000-0000-000000000000",
    "/v1/agent/organizations/00000000-0000-0000-0000-000000000000",
    "/v1/agent/deals/open",
    "/v1/agent/tasks/today",
]


@pytest.mark.parametrize("path", ROUTES)
async def test_every_route_needs_a_token(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ROUTES)
async def test_a_session_login_is_not_a_token(
    client: AsyncClient, alice: Account, path: str
) -> None:
    assert (await client.get(path, headers=alice.headers)).status_code == 401
    assert (await client.get(path, headers={"X-API-Key": "abc"})).status_code == 401


async def test_bearer_and_api_key_both_work(
    client: AsyncClient, alice_token: dict[str, str]
) -> None:
    raw = alice_token["Authorization"].removeprefix("Bearer ")
    assert (await client.get("/v1/agent/deals/open", headers=alice_token)).status_code == 200
    assert (await client.get("/v1/agent/deals/open", headers={"X-API-Key": raw})).status_code == 200


async def test_a_garbage_or_unknown_token_is_refused(client: AsyncClient) -> None:
    for value in ("tc_live_nope", "tc_live_", "Bearer", "x"):
        headers = {"Authorization": f"Bearer {value}"}
        assert (await client.get("/v1/agent/deals/open", headers=headers)).status_code == 401
        assert (
            await client.get("/v1/agent/deals/open", headers={"X-API-Key": value})
        ).status_code == 401


async def test_an_expired_token_is_refused(
    client: AsyncClient,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await session.execute(update(ApiToken).values(expires_at=datetime.now(UTC) - timedelta(1)))
        await session.commit()
    assert (await client.get("/v1/agent/deals/open", headers=alice_token)).status_code == 401


async def test_the_token_of_an_inactive_user_is_refused(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await session.execute(
            update(User).where(User.id == alice.id).values(is_active=False)  # type: ignore[arg-type]
        )
        await session.commit()
    assert (await client.get("/v1/agent/deals/open", headers=alice_token)).status_code == 401


async def test_last_used_is_set_and_not_rewritten_within_a_minute(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def last_used() -> datetime | None:
        listed = (await client.get(TOKENS, headers=alice.headers)).json()
        value = listed[0]["last_used_at"]
        return datetime.fromisoformat(value) if value else None

    assert await last_used() is None
    await client.get("/v1/agent/deals/open", headers=alice_token)
    first = await last_used()
    assert first is not None

    await client.get("/v1/agent/deals/open", headers=alice_token)
    assert await last_used() == first

    # A minute and a bit later it is written again.
    async with session_factory() as session:
        await session.execute(update(ApiToken).values(last_used_at=first - timedelta(minutes=2)))
        await session.commit()
    await client.get("/v1/agent/deals/open", headers=alice_token)
    refreshed = await last_used()
    assert refreshed is not None and refreshed > first - timedelta(minutes=1)


# --- Search ------------------------------------------------------------------


async def test_search_finds_contacts_organizations_and_open_deals(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = Organization(user_id=alice.id, name="Acme GmbH")
    await seed(
        session_factory,
        org,
        Contact(user_id=alice.id, name="Anna Acme", job_title="CTO"),
        deal(alice, "Acme rollout", "proposal"),
        deal(alice, "Acme won deal", "won"),
        deal(alice, "Acme lost deal", "lost"),
        Contact(user_id=alice.id, name="Acme archived", archived_at=NOW),
        Organization(user_id=alice.id, name="Acme archived org", archived_at=NOW),
        deal(alice, "Acme archived deal", archived_at=NOW),
    )

    response = await client.get("/v1/agent/search", params={"q": "acme"}, headers=alice_token)

    assert response.status_code == 200
    body = response.json()
    assert body["q"] == "acme"
    assert [(h["type"], h["title"]) for h in body["hits"]] == [
        ("contact", "Anna Acme"),
        ("organization", "Acme GmbH"),
        ("deal", "Acme rollout"),
    ]
    # Compact: no nulls, no match excerpts or dates.
    assert set(body["hits"][1]) == {"type", "id", "title"}
    assert set(body["hits"][0]) == {"type", "id", "title", "subtitle"}


async def test_search_limit_applies_per_type(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed(session_factory, *(Contact(user_id=alice.id, name=f"Zed {i}") for i in range(4)))
    response = await client.get(
        "/v1/agent/search", params={"q": "zed", "limit": 2}, headers=alice_token
    )
    assert len(response.json()["hits"]) == 2


async def test_search_never_shows_another_tenants_rows(
    client: AsyncClient,
    alice: Account,
    bob: Account,
    bob_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed(
        session_factory,
        Contact(user_id=alice.id, name="Secret Sam"),
        Organization(user_id=alice.id, name="Secret Inc"),
        deal(alice, "Secret deal"),
    )
    response = await client.get("/v1/agent/search", params={"q": "secret"}, headers=bob_token)
    assert response.json()["hits"] == []


@pytest.mark.parametrize("q", ["a", " a ", "", "a\x00b"])
async def test_search_refuses_a_query_it_cannot_run(
    client: AsyncClient, alice_token: dict[str, str], q: str
) -> None:
    response = await client.get("/v1/agent/search", params={"q": q}, headers=alice_token)
    assert response.status_code == 422


async def test_search_refuses_a_limit_over_the_cap(
    client: AsyncClient, alice_token: dict[str, str]
) -> None:
    response = await client.get(
        "/v1/agent/search", params={"q": "ab", "limit": 21}, headers=alice_token
    )
    assert response.status_code == 422


# --- Contacts ----------------------------------------------------------------


async def test_a_contact_comes_with_its_five_latest_interactions(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = Organization(user_id=alice.id, name="Acme GmbH")
    contact = Contact(
        user_id=alice.id,
        name="Anna Berger",
        job_title="CTO",
        organization=org,
        email="anna@acme.test",
        city="Wien",
        country="AT",
        tags=["vip"],
        notes="Met at the conference",
    )
    long_notes = "word  " * 100
    interactions = [
        Interaction(
            user_id=alice.id,
            subject=f"Call {n}",
            kind="call",
            occurred_at=NOW - timedelta(days=n),
            done=True,
            notes=long_notes if n == 1 else None,
            contacts=[contact],
        )
        for n in range(1, 8)
    ]
    other = Contact(user_id=alice.id, name="Someone else")
    await seed(
        session_factory,
        *interactions,
        Interaction(
            user_id=alice.id, subject="Not Anna", occurred_at=NOW, contacts=[other], done=True
        ),
        Interaction(
            user_id=alice.id,
            subject="Archived",
            occurred_at=NOW,
            contacts=[contact],
            archived_at=NOW,
        ),
    )

    response = await client.get(f"/v1/agent/contacts/{contact.id}", headers=alice_token)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Anna Berger"
    assert body["organization"] == {"id": str(org.id), "name": "Acme GmbH"}
    assert body["tags"] == ["vip"]
    assert body["notes"] == "Met at the conference"
    assert "archived" not in body
    assert "phone" not in body  # unset fields are not sent
    recent = body["recent_interactions"]
    assert [i["subject"] for i in recent] == [f"Call {n}" for n in range(1, 6)]
    excerpt = recent[0]["notes_excerpt"]
    assert len(excerpt) <= 281 and excerpt.endswith("…")
    assert "  " not in excerpt
    assert "notes_excerpt" not in recent[1]


async def test_an_archived_contact_is_still_there_but_flagged(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    contact = Contact(user_id=alice.id, name="Old Friend", archived_at=NOW)
    await seed(session_factory, contact)
    body = (await client.get(f"/v1/agent/contacts/{contact.id}", headers=alice_token)).json()
    assert body["archived"] is True


async def test_another_tenants_contact_is_not_found(
    client: AsyncClient,
    alice: Account,
    bob_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    contact = Contact(user_id=alice.id, name="Anna")
    await seed(session_factory, contact)
    response = await client.get(f"/v1/agent/contacts/{contact.id}", headers=bob_token)
    assert response.status_code == 404


# --- Organizations -----------------------------------------------------------


async def test_an_organization_lists_its_people_deals_and_interactions(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = Organization(user_id=alice.id, name="Acme GmbH", domain="acme.test", industry="Tools")
    await seed(
        session_factory,
        org,
        Contact(user_id=alice.id, name="Beta", job_title="CEO", organization=org),
        Contact(user_id=alice.id, name="Alpha", organization=org),
        Contact(user_id=alice.id, name="Archived", organization=org, archived_at=NOW),
        Contact(user_id=alice.id, name="Elsewhere"),
        deal(alice, "Open one", "negotiation", organization=org),
        deal(alice, "Won one", "won", organization=org),
        deal(alice, "Archived one", "lead", organization=org, archived_at=NOW),
        Interaction(
            user_id=alice.id,
            subject="Kickoff",
            kind="meeting",
            occurred_at=NOW,
            done=True,
            organizations=[org],
        ),
    )

    response = await client.get(f"/v1/agent/organizations/{org.id}", headers=alice_token)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Acme GmbH"
    assert body["domain"] == "acme.test"
    assert [c["name"] for c in body["contacts"]] == ["Alpha", "Beta"]
    assert body["contacts"][1]["job_title"] == "CEO"
    assert [(d["title"], d["stage"]) for d in body["open_deals"]] == [("Open one", "negotiation")]
    assert [i["subject"] for i in body["recent_interactions"]] == ["Kickoff"]
    assert "email" not in body


async def test_an_empty_organization_sends_no_empty_lists(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = Organization(user_id=alice.id, name="Lonely")
    await seed(session_factory, org)
    body = (await client.get(f"/v1/agent/organizations/{org.id}", headers=alice_token)).json()
    assert body == {"id": str(org.id), "name": "Lonely"}


async def test_another_tenants_organization_is_not_found(
    client: AsyncClient,
    alice: Account,
    bob_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = Organization(user_id=alice.id, name="Acme")
    await seed(session_factory, org)
    response = await client.get(f"/v1/agent/organizations/{org.id}", headers=bob_token)
    assert response.status_code == 404


# --- Pipeline ----------------------------------------------------------------


@pytest.fixture
def pinned_clock() -> Callable[[datetime], None]:
    def pin(moment: datetime) -> None:
        app.dependency_overrides[current_time] = lambda: moment

    pin(NOW)
    return pin


async def test_the_pipeline_is_the_open_deals_with_totals_per_currency(
    client: AsyncClient,
    alice: Account,
    bob: Account,
    alice_token: dict[str, str],
    pinned_clock: Callable[[datetime], None],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    contact = Contact(user_id=alice.id, name="Anna")
    org = Organization(user_id=alice.id, name="Acme")
    await seed(
        session_factory,
        contact,
        org,
        deal(alice, "Negotiating", "negotiation", fixed_value=Decimal("1000"), currency="EUR"),
        deal(
            alice,
            "Proposal",
            "proposal",
            fixed_value=Decimal("500.50"),
            currency="EUR",
            expected_close_date=NOW.date() + timedelta(days=10),
            probability=40,
            contact=contact,
            organization=org,
        ),
        deal(alice, "Dollar", "lead", fixed_value=Decimal("200"), currency="USD"),
        deal(alice, "Draft", "draft"),
        deal(alice, "Won", "won", fixed_value=Decimal("9999")),
        deal(alice, "Lost", "lost", fixed_value=Decimal("9999")),
        deal(alice, "Archived", "lead", fixed_value=Decimal("9999"), archived_at=NOW),
        deal(bob, "Bob's", "lead", fixed_value=Decimal("9999")),
    )

    response = await client.get("/v1/agent/deals/open", headers=alice_token)

    assert response.status_code == 200
    body = response.json()
    # Stage order: draft, lead, qualified, proposal, negotiation.
    assert [d["title"] for d in body["deals"]] == ["Draft", "Dollar", "Proposal", "Negotiating"]
    assert Decimal(body["totals"]["EUR"]) == Decimal("1500.50")
    assert Decimal(body["totals"]["USD"]) == Decimal("200")
    assert "truncated" not in body
    proposal = body["deals"][2]
    assert proposal["contact_name"] == "Anna"
    assert proposal["organization_name"] == "Acme"
    assert proposal["probability"] == 40
    assert proposal["days_in_stage"] == 3
    assert "probability" not in body["deals"][0]


async def test_the_pipeline_is_truncated_after_200_deals(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed(session_factory, *(deal(alice, f"Deal {i}") for i in range(201)))
    body = (await client.get("/v1/agent/deals/open", headers=alice_token)).json()
    assert len(body["deals"]) == 200
    assert body["truncated"] is True


async def test_an_empty_pipeline(client: AsyncClient, alice_token: dict[str, str]) -> None:
    body = (await client.get("/v1/agent/deals/open", headers=alice_token)).json()
    assert body == {"deals": [], "totals": {}}


# --- Tasks -------------------------------------------------------------------


def task(account: Account, title: str, due: datetime | None, **fields: Any) -> Task:
    fields.setdefault("priority", 0)
    fields.setdefault("done", False)
    return Task(user_id=account.id, title=title, due_date=due, **fields)


async def test_tasks_split_into_overdue_and_today(
    client: AsyncClient,
    alice: Account,
    bob: Account,
    alice_token: dict[str, str],
    pinned_clock: Callable[[datetime], None],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    contact = Contact(user_id=alice.id, name="Anna")
    await seed(
        session_factory,
        contact,
        task(alice, "Slipped", NOW - timedelta(days=2), priority=2, contact=contact),
        task(alice, "Due tonight", datetime(2026, 9, 4, 23, 59, tzinfo=BERLIN)),
        task(alice, "Tomorrow", datetime(2026, 9, 5, 9, 0, tzinfo=BERLIN)),
        task(alice, "Undated", None),
        task(alice, "Done", NOW - timedelta(days=2), done=True),
        task(alice, "Archived", NOW - timedelta(days=2), archived_at=NOW),
        task(bob, "Bob's", NOW - timedelta(days=2)),
    )

    response = await client.get("/v1/agent/tasks/today", headers=alice_token)

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-09-04"
    assert body["timezone"] == "Europe/Berlin"
    assert [t["title"] for t in body["overdue"]] == ["Slipped"]
    assert body["overdue"][0]["days_late"] == 2
    assert body["overdue"][0]["contact_name"] == "Anna"
    assert body["overdue"][0]["priority"] == 2
    assert [t["title"] for t in body["today"]] == ["Due tonight"]
    assert "days_late" not in body["today"][0]


async def test_the_day_follows_the_pinned_clock(
    client: AsyncClient,
    alice: Account,
    alice_token: dict[str, str],
    pinned_clock: Callable[[datetime], None],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed(session_factory, task(alice, "Tomorrow", datetime(2026, 9, 5, 9, 0, tzinfo=BERLIN)))
    pinned_clock(datetime(2026, 9, 5, 7, 0, tzinfo=BERLIN))
    body = (await client.get("/v1/agent/tasks/today", headers=alice_token)).json()
    assert body["date"] == "2026-09-05"
    assert [t["title"] for t in body["today"]] == ["Tomorrow"]
