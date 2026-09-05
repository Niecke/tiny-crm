"""The fields a business actually files on a contact.

Three things here are not plain CRUD:

* the postal address is four columns, so a letter, an invoice and a vCard can
  each take the parts they need;
* the known day rate and its currency are a pair — half of one is refused, the
  same rule the deals router applies to a volume with no unit;
* `works_with_freelancers` is tri-state, and the filter can ask for the
  never-asked ones, because "no" and "never asked" are different answers and
  only one of them is a list worth working through.
"""

from typing import Any

import pytest
from httpx2 import AsyncClient

from tests.conftest import Account, create_resource


async def _contact(client: AsyncClient, account: Account, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": "Maria Rossi"}
    payload.update(fields)
    return await create_resource(client, account, "/contacts/", payload)


async def test_a_contact_carries_everything_a_business_files(
    client: AsyncClient, alice: Account
) -> None:
    contact = await _contact(
        client,
        alice,
        name="Maria Rossi",
        job_title="Head of Delivery",
        email="maria@example.com",
        email_secondary="m.rossi@private.example",
        phone="+43 1 234567",
        phone_secondary="+43 660 1234567",
        website="https://rossi.example",
        street="Hauptstraße 1",
        postal_code="1010",
        city="Wien",
        country="AT",
        lifecycle_status="prospect",
        relation_type="partner",
        source="event",
        preferred_language="de",
        birthday="1980-04-17",
        known_day_rate="850.00",
        rate_currency="EUR",
        works_with_freelancers=True,
    )

    fetched = await client.get(f"/contacts/{contact['id']}", headers=alice.headers)
    assert fetched.status_code == 200
    body = fetched.json()

    assert body["job_title"] == "Head of Delivery"
    assert body["email_secondary"] == "m.rossi@private.example"
    assert body["phone_secondary"] == "+43 660 1234567"
    assert body["website"] == "https://rossi.example"
    # Four parts, not one blob: nothing could split a blob back out afterwards.
    assert body["street"] == "Hauptstraße 1"
    assert body["postal_code"] == "1010"
    assert body["city"] == "Wien"
    assert body["country"] == "AT"
    assert body["lifecycle_status"] == "prospect"
    assert body["relation_type"] == "partner"
    assert body["source"] == "event"
    assert body["preferred_language"] == "de"
    assert body["birthday"] == "1980-04-17"
    # Money is a string end to end — a double cannot hold 0.10.
    assert body["known_day_rate"] == "850.00"
    assert body["rate_currency"] == "EUR"
    assert body["works_with_freelancers"] is True


async def test_a_bare_contact_leaves_every_new_field_unset(
    client: AsyncClient, alice: Account
) -> None:
    contact = await _contact(client, alice, name="Someone From A Card")

    for field in (
        "job_title",
        "email_secondary",
        "phone_secondary",
        "website",
        "street",
        "postal_code",
        "city",
        "country",
        "lifecycle_status",
        "relation_type",
        "source",
        "preferred_language",
        "birthday",
        "known_day_rate",
        "rate_currency",
        # Not False: nobody has been asked yet.
        "works_with_freelancers",
    ):
        assert contact[field] is None, field


async def test_country_and_language_are_normalised(client: AsyncClient, alice: Account) -> None:
    """ "at" and "AT" must not become two countries in a filter."""
    contact = await _contact(client, alice, country="at", preferred_language="DE")

    assert contact["country"] == "AT"
    assert contact["preferred_language"] == "de"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lifecycle_status", "客户"),
        ("relation_type", "friend"),
        ("source", "cold_call"),
        # Alpha-3 is not alpha-2, and "Austria" is not a code at all.
        ("country", "AUT"),
        ("preferred_language", "deu"),
        ("rate_currency", "€"),
        ("birthday", "not-a-date"),
    ],
)
async def test_a_value_outside_the_set_is_refused(
    client: AsyncClient, alice: Account, field: str, value: str
) -> None:
    response = await client.post(
        "/contacts/", json={"name": "Wrong", field: value}, headers=alice.headers
    )

    assert response.status_code == 422


async def test_a_rate_without_its_currency_is_refused(client: AsyncClient, alice: Account) -> None:
    """ "800" is not a rate, the same way "60" is not a volume estimate."""
    response = await client.post(
        "/contacts/",
        json={"name": "Rateless", "known_day_rate": "800.00"},
        headers=alice.headers,
    )

    assert response.status_code == 422
    assert "rate_currency" in response.json()["detail"]


async def test_a_currency_without_a_rate_is_refused(client: AsyncClient, alice: Account) -> None:
    response = await client.post(
        "/contacts/",
        json={"name": "Currency only", "rate_currency": "EUR"},
        headers=alice.headers,
    )

    assert response.status_code == 422


async def test_a_patch_that_would_leave_half_a_rate_is_refused(
    client: AsyncClient, alice: Account
) -> None:
    """The check runs on the merged row, not on what the request mentions."""
    contact = await _contact(client, alice)

    response = await client.patch(
        f"/contacts/{contact['id']}",
        json={"known_day_rate": "900.00"},
        headers=alice.headers,
    )

    assert response.status_code == 422


async def test_a_rate_can_be_added_with_its_currency(client: AsyncClient, alice: Account) -> None:
    contact = await _contact(client, alice)

    response = await client.patch(
        f"/contacts/{contact['id']}",
        json={"known_day_rate": "900.00", "rate_currency": "chf"},
        headers=alice.headers,
    )

    assert response.status_code == 200
    assert response.json()["known_day_rate"] == "900.00"
    assert response.json()["rate_currency"] == "CHF"


async def test_clearing_the_rate_clears_the_currency_with_it(
    client: AsyncClient, alice: Account
) -> None:
    """A currency on its own says nothing, so it goes rather than blocking."""
    contact = await _contact(client, alice, known_day_rate="800.00", rate_currency="EUR")

    response = await client.patch(
        f"/contacts/{contact['id']}",
        json={"known_day_rate": None},
        headers=alice.headers,
    )

    assert response.status_code == 200
    assert response.json()["known_day_rate"] is None
    assert response.json()["rate_currency"] is None


async def test_clearing_the_rate_while_insisting_on_a_currency_is_refused(
    client: AsyncClient, alice: Account
) -> None:
    """Sending the contradiction explicitly is not a tidy-up."""
    contact = await _contact(client, alice, known_day_rate="800.00", rate_currency="EUR")

    response = await client.patch(
        f"/contacts/{contact['id']}",
        json={"known_day_rate": None, "rate_currency": "EUR"},
        headers=alice.headers,
    )

    assert response.status_code == 422


async def test_an_unrelated_patch_leaves_the_rate_alone(
    client: AsyncClient, alice: Account
) -> None:
    contact = await _contact(client, alice, known_day_rate="800.00", rate_currency="EUR")

    response = await client.patch(
        f"/contacts/{contact['id']}", json={"job_title": "CTO"}, headers=alice.headers
    )

    assert response.status_code == 200
    assert response.json()["known_day_rate"] == "800.00"
    assert response.json()["rate_currency"] == "EUR"
    assert response.json()["job_title"] == "CTO"


async def test_never_asked_is_not_the_same_answer_as_no(
    client: AsyncClient, alice: Account
) -> None:
    yes = await _contact(client, alice, name="Yes", works_with_freelancers=True)
    no = await _contact(client, alice, name="No", works_with_freelancers=False)
    unknown = await _contact(client, alice, name="Unknown")

    assert yes["works_with_freelancers"] is True
    assert no["works_with_freelancers"] is False
    assert unknown["works_with_freelancers"] is None


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("yes", ["Yes"]), ("no", ["No"]), ("unknown", ["Unknown"])],
)
async def test_the_freelancer_filter_can_ask_all_three_questions(
    client: AsyncClient, alice: Account, answer: str, expected: list[str]
) -> None:
    """A plain bool parameter could not ask for the never-asked ones."""
    await _contact(client, alice, name="Yes", works_with_freelancers=True)
    await _contact(client, alice, name="No", works_with_freelancers=False)
    await _contact(client, alice, name="Unknown")

    response = await client.get(
        f"/contacts/?works_with_freelancers={answer}", headers=alice.headers
    )

    assert response.status_code == 200
    assert [c["name"] for c in response.json()["items"]] == expected


async def test_status_and_type_filter_independently(client: AsyncClient, alice: Account) -> None:
    """Two questions, two filters — collapsing them would lose this row."""
    await _contact(client, alice, name="Untouched partner", relation_type="partner")
    await _contact(
        client,
        alice,
        name="Partner we sell to",
        relation_type="partner",
        lifecycle_status="customer",
    )
    await _contact(client, alice, name="Plain customer", lifecycle_status="customer")

    by_type = await client.get("/contacts/?relation_type=partner", headers=alice.headers)
    by_status = await client.get("/contacts/?lifecycle_status=customer", headers=alice.headers)

    assert by_type.json()["total"] == 2
    assert by_status.json()["total"] == 2


async def test_two_filters_narrow_rather_than_widen(client: AsyncClient, alice: Account) -> None:
    """ "Partners we have not approached yet" is one request."""
    await _contact(client, alice, name="Untouched partner", relation_type="partner")
    await _contact(
        client,
        alice,
        name="Partner we sell to",
        relation_type="partner",
        lifecycle_status="customer",
    )

    response = await client.get(
        "/contacts/?relation_type=partner&lifecycle_status=lead", headers=alice.headers
    )

    assert response.json()["total"] == 0

    await _contact(
        client,
        alice,
        name="Fresh partner",
        relation_type="partner",
        lifecycle_status="lead",
    )

    narrowed = await client.get(
        "/contacts/?relation_type=partner&lifecycle_status=lead", headers=alice.headers
    )
    assert [c["name"] for c in narrowed.json()["items"]] == ["Fresh partner"]


async def test_source_and_country_are_filterable(client: AsyncClient, alice: Account) -> None:
    await _contact(client, alice, name="From a tender", source="tender_portal", country="AT")
    await _contact(client, alice, name="From a referral", source="referral", country="DE")

    by_source = await client.get("/contacts/?source=tender_portal", headers=alice.headers)
    # Lower case on the way in, because a filter that depends on how the caller
    # typed it is not a filter.
    by_country = await client.get("/contacts/?country=de", headers=alice.headers)

    assert [c["name"] for c in by_source.json()["items"]] == ["From a tender"]
    assert [c["name"] for c in by_country.json()["items"]] == ["From a referral"]


async def test_an_unknown_filter_value_is_refused_rather_than_ignored(
    client: AsyncClient, alice: Account
) -> None:
    """Silently ignoring it would show every contact and look like an answer."""
    assert (
        await client.get("/contacts/?lifecycle_status=customerish", headers=alice.headers)
    ).status_code == 422
    assert (
        await client.get("/contacts/?works_with_freelancers=maybe", headers=alice.headers)
    ).status_code == 422
