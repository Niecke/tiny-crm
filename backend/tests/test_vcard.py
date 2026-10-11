"""Tests for vCard export and import."""

import io

from httpx2 import AsyncClient

from app.importers.vcard import parse_vcards
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
