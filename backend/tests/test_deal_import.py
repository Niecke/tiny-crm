"""Tests for Deal import (specifically the lead_generation format)."""

import io

from httpx2 import AsyncClient

from tests.conftest import Account


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
