"""Importer for lead_generation tool output CSVs (e.g. hot_leads.csv).

Ingests scored company leads into Organization and Deal records with stage='lead',
preserving all research insights, entry angles, and Firmenbuch data.
"""

from __future__ import annotations

import csv
import io
import sys
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_update, snapshot
from app.db import one_at_a_time
from app.models.deal import Deal
from app.models.organization import Organization
from app.schemas.import_export import DealImportSummary

if TYPE_CHECKING:
    from app.auth.users import User

# Accommodate large CSV cells up to 10 MB without crashing
csv.field_size_limit(min(sys.maxsize, 10 * 1024 * 1024))


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


def _nothing_imported(errors: list[str], total_rows: int = 0) -> DealImportSummary:
    return DealImportSummary(
        format="lead_generation",
        total_rows=total_rows,
        imported_deals=0,
        created_organizations=0,
        skipped_duplicates=0,
        errors=errors,
    )


async def import_lead_generation_deals(
    session: AsyncSession,
    user: User,
    csv_text: str,
) -> DealImportSummary:
    """Ingest CSV formatted by the cc lead_generation tool into Organizations and Deals.

    One deal per company, and only once: a row whose organization already has a
    deal — in any stage, renamed or archived since — is skipped, and so is a row
    for an organization that was archived. The tool rewords its entry angles
    between runs, so the deal title cannot say whether a lead was imported
    before; the company can.
    """
    from app.routers.deals import apply_stage

    # newline="" leaves line endings to the csv module, as its documentation
    # asks: a file with bare CRs (old Mac, some Excel exports) is then rows, not
    # one line with "new-line character seen in unquoted field".
    reader = csv.DictReader(io.StringIO(csv_text, newline=""))
    try:
        fieldnames = reader.fieldnames
    except csv.Error as exc:
        return _nothing_imported([f"CSV format error: {exc}"])
    if not fieldnames:
        return _nothing_imported(["Empty or invalid CSV file."])

    # Normalize header mapping
    headers = {h.strip().lower(): h for h in fieldnames if h}
    if not any(k in headers for k in ("company", "company_name")):
        return _nothing_imported(["Missing required 'company' column in CSV."])

    # The same file sent from two tabs would otherwise pass each other's
    # duplicate check: both read "not there yet" before either commits.
    await one_at_a_time(session, f"import:{user.id}")

    # Cache existing organizations to minimize queries. Archived ones included,
    # so a company that was put away is recognised rather than created again.
    # Sorted archived-first: where two share a name, the live one wins the key.
    org_res = await session.execute(select(Organization).where(Organization.user_id == user.id))
    existing_orgs = sorted(org_res.scalars().all(), key=lambda o: o.archived_at is None)
    orgs_by_name = {o.name.lower(): o for o in existing_orgs}
    orgs_by_domain = {o.domain.lower(): o for o in existing_orgs if o.domain}

    # Archived deals count too: archiving a lead is a decision about it, and a
    # re-import must not undo that by creating it afresh.
    deal_res = await session.execute(
        select(Deal.organization_id)
        .where(Deal.user_id == user.id, Deal.organization_id.is_not(None))
        .distinct()
    )
    orgs_with_deal = set(deal_res.scalars().all())

    total_rows = 0
    imported_deals = 0
    created_organizations = 0
    skipped_duplicates = 0
    errors: list[str] = []

    try:
        for row_idx, raw_row in enumerate(reader, start=2):
            if not any(raw_row.values()):
                continue

            row = {k.strip().lower(): _clean(v) for k, v in raw_row.items() if k}
            company = row.get("company") or row.get("company_name", "")
            if not company:
                errors.append(f"Row {row_idx}: Missing required company name.")
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

            if org is not None and org.archived_at is not None:
                skipped_duplicates += 1
                continue

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
                created_organizations += 1
            elif domain and not org.domain:
                # An edit like any other, so it gets its history entry: a form
                # opened before the import is refused as stale, and the history
                # has to be able to say why.
                before = snapshot(org)
                org.domain = domain
                record_update(session, user, org, before)

            # Both keys, every time: a later row may name this company by the
            # spelling or the domain that only this row brought along.
            orgs_by_name.setdefault(company.lower(), org)
            if org.domain:
                orgs_by_domain.setdefault(org.domain.lower(), org)

            # 2. One deal per company
            if org.id in orgs_with_deal:
                skipped_duplicates += 1
                continue

            # 3. Derive Deal title
            entry_angle = row.get("entry_angle", "")
            if entry_angle:
                deal_title = entry_angle if len(entry_angle) <= 160 else entry_angle[:157] + "..."
            else:
                deal_title = f"{company} Consulting"

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
            orgs_with_deal.add(org.id)
            imported_deals += 1

        await session.commit()
    except csv.Error as exc:
        # All or nothing. The rows before the broken one were only pending, and
        # reporting them as imported would send the operator looking for deals
        # that do not exist.
        await session.rollback()
        errors.append(f"CSV format error near line {reader.line_num}: {exc}. Nothing was imported.")
        return _nothing_imported(errors, total_rows)

    return DealImportSummary(
        format="lead_generation",
        total_rows=total_rows,
        imported_deals=imported_deals,
        created_organizations=created_organizations,
        skipped_duplicates=skipped_duplicates,
        errors=errors,
    )
