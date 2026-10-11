"""Tests for Deal import (specifically the lead_generation format)."""

import csv
import io
from typing import Any

from httpx2 import AsyncClient

from tests.conftest import Account, create_resource


async def test_import_lead_generation_deals(client: AsyncClient, alice: Account) -> None:
    csv_content = (
        "company,category,score,verdict,entry_angle,reason,domain,fn,plz,legal_form,contacted_at,checked_at\n"
        'Andromeda Software GmbH,Client,9,Hot,"GCP Multi-Region Architecture","Austrian ISV.",'
        "andromeda.example,34612a,1010,GmbH,,2026-10-07\n"
        'APUS Software GmbH,Client,8,Hot,"Cloud audit for IONIO.","Healthcare platform.",'
        "apus.example,48266f,8010,GmbH,,2026-10-07"
    )

    files = {"file": ("hot_leads.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = await client.post(
        "/deals/import?format=lead_generation",
        files=files,
        headers=alice.headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["format"] == "lead_generation"
    assert data["total_rows"] == 2
    assert data["imported_deals"] == 2
    assert data["created_organizations"] == 2
    assert data["skipped_duplicates"] == 0

    # Verify deals were created in 'lead' stage and linked to organization
    deals_res = await client.get("/deals/?stage=lead", headers=alice.headers)
    assert deals_res.status_code == 200
    deal_items = deals_res.json()["items"]
    assert len(deal_items) >= 2

    andromeda_deal = next(
        (d for d in deal_items if "Andromeda Software GmbH" in (d["organization_name"] or "")),
        None,
    )
    assert andromeda_deal is not None
    assert andromeda_deal["stage"] == "lead"
    assert "**Score**: 9/10 (Hot)" in andromeda_deal["notes"]
    assert "**Firmenbuch**: 34612a" in andromeda_deal["notes"]

    # Re-importing the same CSV should be idempotent and skip duplicates
    files_again = {"file": ("hot_leads.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    re_response = await client.post(
        "/deals/import?format=lead_generation",
        files=files_again,
        headers=alice.headers,
    )
    assert re_response.status_code == 200
    re_data = re_response.json()
    assert re_data["imported_deals"] == 0
    assert re_data["created_organizations"] == 0
    assert re_data["skipped_duplicates"] == 2


async def test_import_deals_rejects_unsupported_format(client: AsyncClient, alice: Account) -> None:
    files = {"file": ("leads.csv", io.BytesIO(b"a,b,c"), "text/csv")}
    response = await client.post(
        "/deals/import?format=unsupported_tool",
        files=files,
        headers=alice.headers,
    )
    assert response.status_code == 422
    assert "Unsupported format" in response.json()["detail"]


async def test_import_deals_handles_invalid_csv(client: AsyncClient, alice: Account) -> None:
    # Missing company header
    files = {"file": ("bad.csv", io.BytesIO(b"foo,bar\n1,2"), "text/csv")}
    response = await client.post(
        "/deals/import?format=lead_generation",
        files=files,
        headers=alice.headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["imported_deals"] == 0
    assert len(data["errors"]) > 0
    assert "company" in data["errors"][0]


async def test_import_actual_hot_leads_file(client: AsyncClient, alice: Account) -> None:
    from pathlib import Path

    hot_leads_path = Path(__file__).parent / "fixtures" / "hot_leads.csv"
    assert hot_leads_path.exists(), "Test fixture hot_leads.csv must exist"
    content = hot_leads_path.read_bytes()
    files = {"file": ("hot_leads.csv", io.BytesIO(content), "text/csv")}
    response = await client.post(
        "/deals/import?format=lead_generation",
        files=files,
        headers=alice.headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["imported_deals"] == 20
    assert data["created_organizations"] == 20
    assert data["skipped_duplicates"] == 0


async def _import(client: AsyncClient, account: Account, content: str | bytes) -> dict[str, Any]:
    data = content.encode("utf-8") if isinstance(content, str) else content
    files = {"file": ("hot_leads.csv", io.BytesIO(data), "text/csv")}
    response = await client.post(
        "/deals/import?format=lead_generation", files=files, headers=account.headers
    )
    assert response.status_code == 200, response.text
    summary: dict[str, Any] = response.json()
    return summary


async def _deal_count(client: AsyncClient, account: Account, query: str = "") -> int:
    response = await client.get(f"/deals/{query}", headers=account.headers)
    assert response.status_code == 200, response.text
    total: int = response.json()["total"]
    return total


async def test_bare_carriage_returns_are_line_endings(client: AsyncClient, alice: Account) -> None:
    summary = await _import(client, alice, "company,entry_angle\rAcme GmbH,Cloud audit\rBeta AG,\r")
    assert summary["errors"] == []
    assert summary["imported_deals"] == 2


async def test_a_csv_error_imports_nothing_and_says_so(client: AsyncClient, alice: Account) -> None:
    # The real limit equals the upload cap, so no upload reaches it; a small one
    # stands in for whatever the csv module refuses next.
    previous = csv.field_size_limit(50)
    try:
        summary = await _import(
            client, alice, f"company,reason\nAcme GmbH,fine\nBeta AG,{'x' * 51}\n"
        )
    finally:
        csv.field_size_limit(previous)

    assert summary["imported_deals"] == 0
    assert summary["created_organizations"] == 0
    assert "Nothing was imported" in summary["errors"][-1]
    assert await _deal_count(client, alice) == 0
    organizations = await client.get("/organizations/", headers=alice.headers)
    assert organizations.json()["total"] == 0


async def test_a_lead_is_imported_once_whatever_became_of_it(
    client: AsyncClient, alice: Account
) -> None:
    """Archived, renamed, or reworded by the tool since: still the same lead."""
    first = (
        "company,entry_angle\n"
        "Acme GmbH,Cloud audit\n"
        "Beta AG,Kubernetes migration\n"
        "Gamma KG,FinOps review\n"
    )
    assert (await _import(client, alice, first))["imported_deals"] == 3

    listed = await client.get("/deals/", headers=alice.headers)
    by_company = {d["organization_name"]: d for d in listed.json()["items"]}
    archived = await client.post(
        f"/deals/{by_company['Acme GmbH']['id']}/archive", headers=alice.headers
    )
    assert archived.status_code == 200, archived.text
    renamed = await client.patch(
        f"/deals/{by_company['Beta AG']['id']}",
        json={"title": "Beta: platform rebuild"},
        headers=alice.headers,
    )
    assert renamed.status_code == 200, renamed.text

    next_week = (
        "company,entry_angle\n"
        "Acme GmbH,Cloud audit\n"
        "BETA AG,Kubernetes migration\n"
        "Gamma KG,A FinOps review of their GCP bill\n"
        "Delta OG,Landing zone\n"
    )
    summary = await _import(client, alice, next_week)
    assert (summary["imported_deals"], summary["skipped_duplicates"]) == (1, 3)
    assert summary["created_organizations"] == 1
    assert await _deal_count(client, alice) == 3
    assert await _deal_count(client, alice, "?archived=true") == 1


async def test_an_archived_organization_is_not_created_again(
    client: AsyncClient, alice: Account
) -> None:
    org = await create_resource(client, alice, "/organizations/", {"name": "Acme GmbH"})
    await client.post(f"/organizations/{org['id']}/archive", headers=alice.headers)

    summary = await _import(client, alice, "company,entry_angle\nAcme GmbH,Cloud audit\n")
    assert (summary["imported_deals"], summary["created_organizations"]) == (0, 0)
    assert summary["skipped_duplicates"] == 1
    live = await client.get("/organizations/", headers=alice.headers)
    assert live.json()["total"] == 0


async def test_one_company_under_two_spellings_stays_one(
    client: AsyncClient, alice: Account
) -> None:
    """The domain a row fills in is what the next row is recognised by."""
    org = await create_resource(client, alice, "/organizations/", {"name": "Acme"})

    summary = await _import(
        client,
        alice,
        "company,domain,entry_angle\n"
        "Acme,acme.example,Cloud audit\n"
        "Acme Holding GmbH,acme.example,Cloud audit for the holding\n"
        "ACME HOLDING GMBH,,Third spelling\n",
    )
    assert summary["created_organizations"] == 0
    assert (summary["imported_deals"], summary["skipped_duplicates"]) == (1, 2)

    [deal] = (await client.get("/deals/", headers=alice.headers)).json()["items"]
    assert deal["organization_id"] == org["id"]


async def test_a_filled_in_domain_is_in_the_organizations_history(
    client: AsyncClient, alice: Account
) -> None:
    org = await create_resource(client, alice, "/organizations/", {"name": "Acme GmbH"})

    await _import(client, alice, "company,domain\nAcme GmbH,acme.example\n")

    history = await client.get(f"/history/organization/{org['id']}", headers=alice.headers)
    assert history.status_code == 200, history.text
    [entry] = history.json()["items"]
    assert entry["action"] == "update"
    assert entry["changes"] == {"domain": {"old": None, "new": "acme.example"}}

    # And importing it again changes nothing, so it records nothing.
    await _import(client, alice, "company,domain\nAcme GmbH,acme.example\n")
    again = await client.get(f"/history/organization/{org['id']}", headers=alice.headers)
    assert again.json()["total"] == 1
