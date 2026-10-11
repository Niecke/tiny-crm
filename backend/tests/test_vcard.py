"""Tests for vCard export and import."""

import io
from typing import Any
from urllib.parse import quote

from httpx2 import AsyncClient

from app.importers.vcard import _normalize_country, parse_vcards
from tests.conftest import Account, create_resource


def test_parse_vcards_handles_folding_and_unescaping() -> None:
    sample = """BEGIN:VCARD
VERSION:3.0
FN:Dr. Jane Doe
TITLE:Chief Technical
  Officer
ORG:Acme\\;Corp
EMAIL;TYPE=PREF:jane@acme.example
EMAIL:secondary@acme.example
TEL;TYPE=VOICE:+43 1 23456
TEL;TYPE=CELL:+43 660 99999
URL:https://acme.example
ADR;TYPE=WORK:;;Main Street 1;Vienna;;1010;Austria
BDAY:1985-04-12
CATEGORIES:VIP,Engineering
NOTE:Met at cloud conference.\\nFollow up next week.
END:VCARD"""

    parsed = parse_vcards(sample)
    assert len(parsed) == 1
    card = parsed[0]
    assert card.name == "Dr. Jane Doe"
    assert card.job_title == "Chief Technical Officer"
    assert card.organization_name == "Acme;Corp"
    assert card.email == "jane@acme.example"
    assert card.email_secondary == "secondary@acme.example"
    assert card.phone == "+43 1 23456"
    assert card.phone_secondary == "+43 660 99999"
    assert card.website == "https://acme.example"
    assert card.street == "Main Street 1"
    assert card.city == "Vienna"
    assert card.postal_code == "1010"
    assert card.country == "AT"
    assert card.tags == ["VIP", "Engineering"]
    assert card.notes == "Met at cloud conference.\nFollow up next week."


async def test_export_single_contact_vcard(client: AsyncClient, alice: Account) -> None:
    org = await create_resource(client, alice, "/organizations/", {"name": "Globex"})
    contact = await create_resource(
        client,
        alice,
        "/contacts/",
        {
            "name": "Homer Simpson",
            "job_title": "Safety Inspector",
            "organization_id": org["id"],
            "email": "homer@globex.example",
            "street": "742 Evergreen Terrace",
            "city": "Springfield",
            "postal_code": "12345",
            "country": "US",
            "tags": ["nuclear", "donut"],
        },
    )

    response = await client.get(f"/contacts/{contact['id']}/vcard", headers=alice.headers)
    assert response.status_code == 200
    assert "text/vcard" in response.headers["content-type"]
    assert 'filename="Homer_Simpson.vcf"' in response.headers["content-disposition"]
    body = response.text
    assert "BEGIN:VCARD" in body
    assert "FN:Homer Simpson" in body
    assert "TITLE:Safety Inspector" in body
    assert "ORG:Globex" in body
    assert "EMAIL;TYPE=INTERNET,PREF:homer@globex.example" in body
    assert "CATEGORIES:nuclear,donut" in body
    assert "END:VCARD" in body


async def test_export_all_contacts_vcard(client: AsyncClient, alice: Account) -> None:
    await create_resource(client, alice, "/contacts/", {"name": "Alice Contact 1"})
    await create_resource(client, alice, "/contacts/", {"name": "Alice Contact 2"})

    response = await client.get("/contacts/vcard", headers=alice.headers)
    assert response.status_code == 200
    assert "text/vcard" in response.headers["content-type"]
    assert 'filename="contacts.vcf"' in response.headers["content-disposition"]
    body = response.text
    assert body.count("BEGIN:VCARD") >= 2
    assert "FN:Alice Contact 1" in body
    assert "FN:Alice Contact 2" in body


async def test_import_contacts_vcard(client: AsyncClient, alice: Account) -> None:
    vcf_content = """BEGIN:VCARD
VERSION:3.0
FN:Marge Simpson
TITLE:Homemaker
ORG:Springfield Civic
EMAIL:marge@springfield.example
CATEGORIES:Family
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Bart Simpson
ORG:Springfield Elementary
NOTE:Troublemaker
END:VCARD"""

    files = {"file": ("contacts.vcf", io.BytesIO(vcf_content.encode("utf-8")), "text/vcard")}
    response = await client.post("/contacts/import/vcard", files=files, headers=alice.headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total_cards"] == 2
    assert data["imported_contacts"] == 2
    assert data["created_organizations"] == 2

    # Verify contacts in database
    list_res = await client.get("/contacts/?search=Marge", headers=alice.headers)
    assert list_res.status_code == 200
    marge = list_res.json()["items"][0]
    assert marge["name"] == "Marge Simpson"
    assert marge["job_title"] == "Homemaker"
    assert marge["organization_name"] == "Springfield Civic"


def _card(*lines: str) -> str:
    return "\n".join(["BEGIN:VCARD", "VERSION:3.0", *lines, "END:VCARD"])


async def _import(client: AsyncClient, account: Account, text: str) -> dict[str, Any]:
    files = {"file": ("contacts.vcf", io.BytesIO(text.encode("utf-8")), "text/vcard")}
    response = await client.post("/contacts/import/vcard", files=files, headers=account.headers)
    assert response.status_code == 200, response.text
    summary: dict[str, Any] = response.json()
    return summary


def test_grouped_properties_are_read_like_plain_ones() -> None:
    """Apple and Google hang labels on a property by grouping it: item1.EMAIL."""
    [card] = parse_vcards(
        _card(
            "FN:Jane Doe",
            "item1.EMAIL;type=INTERNET:jane@acme.example",
            "item1.X-ABLabel:Work",
            "item2.TEL:+43 1 23456",
            "item3.ADR:;;Ring 1;Wien;;1010;Austria",
            "item4.URL:https://acme.example",
        )
    )
    assert card.email == "jane@acme.example"
    assert card.phone == "+43 1 23456"
    assert (card.street, card.city, card.postal_code, card.country) == (
        "Ring 1",
        "Wien",
        "1010",
        "AT",
    )
    assert card.website == "https://acme.example"


def test_quoted_printable_values_are_decoded() -> None:
    """Android's default export: vCard 2.1, soft line breaks and all."""
    sample = "\r\n".join(
        [
            "BEGIN:VCARD",
            "VERSION:2.1",
            "N;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:M=C3=BCller;J=C3=BCrgen;;;",
            "FN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:J=C3=BCrgen M=C3=BCller",
            "ORG;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:M=C3=BCller =26 S=C3=B6hne",
            "NOTE;ENCODING=QUOTED-PRINTABLE:Erste Zeile=0AZweite Zeile, die so lang ist, dass=",
            " sie umbricht",
            "TEL;CELL:+43 660 99999",
            "END:VCARD",
        ]
    )
    [card] = parse_vcards(sample)
    assert card.name == "Jürgen Müller"
    assert card.organization_name == "Müller & Söhne"
    assert card.notes == "Erste Zeile\nZweite Zeile, die so lang ist, dass sie umbricht"
    assert card.phone_secondary == "+43 660 99999"


def test_quoted_printable_in_another_charset() -> None:
    [card] = parse_vcards(
        "BEGIN:VCARD\nVERSION:2.1\n"
        "FN;CHARSET=ISO-8859-1;ENCODING=QUOTED-PRINTABLE:J=FCrgen\nEND:VCARD"
    )
    assert card.name == "Jürgen"


def test_one_address_is_taken_whole() -> None:
    """Two ADRs are two addresses, not one to be assembled from both."""
    [card] = parse_vcards(
        _card(
            "FN:Jane Doe",
            "ADR;TYPE=WORK:;;Ring 1;Wien;;1010;Austria",
            "ADR;TYPE=HOME:;;Dorfstr 5;Graz;;;",
        )
    )
    assert (card.street, card.city, card.postal_code, card.country) == (
        "Ring 1",
        "Wien",
        "1010",
        "AT",
    )


def test_the_preferred_address_wins_over_the_first() -> None:
    [card] = parse_vcards(
        _card(
            "FN:Jane Doe",
            "ADR;TYPE=WORK:;;Ring 1;Wien;;1010;Austria",
            "ADR;TYPE=HOME,PREF:;;Dorfstr 5;Graz;;;Atlantis",
        )
    )
    # No code for the country, so it stays readable on the city line — and the
    # other address's "AT" does not stay behind.
    assert (card.street, card.city, card.postal_code, card.country) == (
        "Dorfstr 5",
        "Graz, Atlantis",
        None,
        None,
    )


def test_preferred_email_and_phone_come_first() -> None:
    [card] = parse_vcards(
        _card(
            "FN:Jane Doe",
            "EMAIL:other@acme.example",
            "EMAIL;TYPE=INTERNET,PREF:jane@acme.example",
            "TEL;TYPE=WORK:+43 1 23456",
            "TEL;TYPE=CELL,PREF:+43 660 99999",
        )
    )
    assert (card.email, card.email_secondary) == ("jane@acme.example", "other@acme.example")
    assert (card.phone, card.phone_secondary) == ("+43 660 99999", "+43 1 23456")


def test_country_names_and_codes() -> None:
    assert _normalize_country("Österreich") == "AT"
    assert _normalize_country("de") == "DE"
    # Not a code of its own: the ISO code for the United Kingdom is GB.
    assert _normalize_country("UK") == "GB"
    # Two letters, but not two the column's readers accept.
    assert _normalize_country("日本") is None
    assert _normalize_country("Atlantis") is None


async def test_a_non_ascii_country_does_not_break_the_contact_list(
    client: AsyncClient, alice: Account
) -> None:
    summary = await _import(client, alice, _card("FN:Taro Yamada", "ADR:;;;Tokyo;;;日本"))
    assert summary["imported_contacts"] == 1

    listed = await client.get("/contacts/", headers=alice.headers)
    assert listed.status_code == 200, listed.text
    [taro] = listed.json()["items"]
    assert taro["country"] is None
    assert taro["city"] == "Tokyo, 日本"


async def test_export_filename_survives_a_non_latin_name(
    client: AsyncClient, alice: Account
) -> None:
    for name in ("Jiří Novák", "李雷"):
        contact = await create_resource(client, alice, "/contacts/", {"name": name})
        response = await client.get(f"/contacts/{contact['id']}/vcard", headers=alice.headers)
        assert response.status_code == 200, response.text
        disposition = response.headers["content-disposition"]
        # ASCII for clients that read nothing else, the real name beside it.
        assert disposition.isascii()
        assert f"filename*=UTF-8''{quote(name + '.vcf', safe='')}" in disposition

    assert 'filename="contact.vcf"' in disposition


async def test_importing_twice_creates_nothing_new(client: AsyncClient, alice: Account) -> None:
    vcf = "\n".join(
        [
            _card("FN:Marge Simpson", "EMAIL:marge@springfield.example"),
            _card("FN:Bart Simpson"),
            # The same card again, further down the same file.
            _card("FN:Marge Simpson", "EMAIL:MARGE@springfield.example"),
            # Same name, another address: somebody else.
            _card("FN:Marge Simpson", "EMAIL:other.marge@shelbyville.example"),
        ]
    )
    first = await _import(client, alice, vcf)
    assert (first["total_cards"], first["imported_contacts"], first["skipped_duplicates"]) == (
        4,
        3,
        1,
    )

    again = await _import(client, alice, vcf)
    assert (again["imported_contacts"], again["skipped_duplicates"]) == (0, 4)

    listed = await client.get("/contacts/", headers=alice.headers)
    assert listed.json()["total"] == 3


async def test_importing_an_export_creates_nothing_new(client: AsyncClient, alice: Account) -> None:
    await create_resource(
        client, alice, "/contacts/", {"name": "Homer Simpson", "email": "homer@globex.example"}
    )
    # Only a second address, which the export writes as its only EMAIL.
    await create_resource(
        client, alice, "/contacts/", {"name": "Lenny", "email_secondary": "lenny@globex.example"}
    )
    archived = await create_resource(client, alice, "/contacts/", {"name": "Carl"})
    await client.post(f"/contacts/{archived['id']}/archive", headers=alice.headers)

    live = await client.get("/contacts/vcard", headers=alice.headers)
    put_away = await client.get("/contacts/vcard?archived=true", headers=alice.headers)

    summary = await _import(client, alice, live.text + put_away.text)
    assert (summary["imported_contacts"], summary["skipped_duplicates"]) == (0, 3)


async def test_cards_without_a_name_are_reported(client: AsyncClient, alice: Account) -> None:
    vcf = "\n".join([_card("FN:Marge Simpson"), _card("EMAIL:nobody@springfield.example")])
    summary = await _import(client, alice, vcf)
    assert summary["total_cards"] == 2
    assert summary["imported_contacts"] == 1
    assert summary["errors"] == ["Card 2: no name (FN or N), skipped."]
