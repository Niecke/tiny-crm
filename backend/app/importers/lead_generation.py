"""Importer for lead_generation tool output CSVs (e.g. hot_leads.csv).

Ingests scored company leads into Organization and Deal records with stage='lead',
preserving all research insights, entry angles, and Firmenbuch data.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import live
from app.models.deal import Deal
from app.models.organization import Organization
from app.schemas.import_export import DealImportSummary

if TYPE_CHECKING:
    from app.auth.users import User


def _clean(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _format_deal_notes(row: dict[str, str]) -> str:
    lines: list[str] = ["### Lead Generation"]

    score = _clean(row.get("score"))
    verdict = _clean(row.get("verdict"))
    if score or verdict:
        score_desc = (
            f"- **Score**: {score}/10 ({verdict})" if verdict else f"- **Score**: {score}/10"
        )
        lines.append(score_desc)

    category = _clean(row.get("category"))
    if category:
        lines.append(f"- **Category**: {category}")

    entry_angle = _clean(row.get("entry_angle"))
    if entry_angle:
        lines.append(f"- **Entry Angle**: {entry_angle}")

    reason = _clean(row.get("reason"))
    if reason:
        lines.append(f"- **Reason**: {reason}")

    fn = _clean(row.get("fn"))
    if fn:
        lines.append(f"- **Firmenbuch**: {fn}")

    legal_form = _clean(row.get("legal_form"))
    if legal_form:
        lines.append(f"- **Legal Form**: {legal_form}")

    plz = _clean(row.get("plz"))
    if plz:
        lines.append(f"- **PLZ**: {plz}")

    checked_at = _clean(row.get("checked_at"))
    if checked_at:
        lines.append(f"- **Checked At**: {checked_at}")

    contacted_at = _clean(row.get("contacted_at"))
    if contacted_at:
        lines.append(f"- **Contacted At**: {contacted_at}")

    return "\n".join(lines)


async def import_lead_generation_deals(
    session: AsyncSession,
    user: User,
    csv_text: str,
) -> DealImportSummary:
    """Ingest CSV formatted by the cc lead_generation tool into Organizations and Deals."""
    from app.routers.deals import apply_stage

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return DealImportSummary(
            format="lead_generation",
            total_rows=0,
            imported_deals=0,
            created_organizations=0,
            skipped_duplicates=0,
            errors=["Empty or invalid CSV file."],
        )

    # Normalize header mapping
    headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    if not any(k in headers for k in ("company", "company_name")):
        return DealImportSummary(
            format="lead_generation",
            total_rows=0,
            imported_deals=0,
            created_organizations=0,
            skipped_duplicates=0,
            errors=["Missing required 'company' column in CSV."],
        )

    # Cache existing organizations to minimize queries
    org_stmt = select(Organization).where(Organization.user_id == user.id, live(Organization))
    org_res = await session.execute(org_stmt)
    existing_orgs = list(org_res.scalars().all())
    orgs_by_name = {o.name.lower(): o for o in existing_orgs}
    orgs_by_domain = {o.domain.lower(): o for o in existing_orgs if o.domain}

    total_rows = 0
    imported_deals = 0
    created_organizations = 0
    skipped_duplicates = 0
    errors: list[str] = []

    for raw_row in reader:
        row = {k.strip().lower(): _clean(v) for k, v in raw_row.items() if k}
        company = row.get("company") or row.get("company_name", "")
        if not company:
            continue

        total_rows += 1
        domain = row.get("domain") or row.get("website", "")
        fn = row.get("fn", "")
        legal_form = row.get("legal_form", "")
        plz = row.get("plz", "")

        # 1. Resolve or create Organization
        org = orgs_by_name.get(company.lower())
        if org is None and domain:
            org = orgs_by_domain.get(domain.lower())

        if org is None:
            notes_parts = []
            if fn:
                notes_parts.append(f"Firmenbuch: {fn}")
            if legal_form:
                notes_parts.append(f"Rechtsform: {legal_form}")
            if plz:
                notes_parts.append(f"PLZ: {plz}")

            org = Organization(
                name=company,
                domain=domain or None,
                notes=" | ".join(notes_parts) if notes_parts else None,
                user_id=user.id,
            )
            session.add(org)
            await session.flush()
            orgs_by_name[company.lower()] = org
            if domain:
                orgs_by_domain[domain.lower()] = org
            created_organizations += 1
        elif domain and not org.domain:
            org.domain = domain

        # 2. Derive Deal title
        entry_angle = row.get("entry_angle", "")
        if entry_angle:
            deal_title = entry_angle if len(entry_angle) <= 160 else entry_angle[:157] + "..."
        else:
            deal_title = f"{company} Consulting"

        # 3. Check for duplicate Deal for this organization
        existing_deal_query = select(Deal).where(
            Deal.user_id == user.id,
            Deal.organization_id == org.id,
            live(Deal),
            func.lower(Deal.title) == func.lower(deal_title),
        )
        existing_deal = await session.scalar(existing_deal_query)
        if existing_deal is not None:
            skipped_duplicates += 1
            continue

        # 4. Create new Deal in 'lead' stage
        notes = _format_deal_notes(row)
        deal = Deal(
            title=deal_title,
            organization_id=org.id,
            notes=notes,
            user_id=user.id,
            value_type="fixed",
        )
        apply_stage(deal, "lead", None)
        session.add(deal)
        imported_deals += 1

    await session.commit()

    return DealImportSummary(
        format="lead_generation",
        total_rows=total_rows,
        imported_deals=imported_deals,
        created_organizations=created_organizations,
        skipped_duplicates=skipped_duplicates,
        errors=errors,
    )
