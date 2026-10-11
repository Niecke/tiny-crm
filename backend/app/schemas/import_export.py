from pydantic import BaseModel


class DealImportSummary(BaseModel):
    """Result of importing deals from a batch file (e.g. lead_generation)."""

    format: str
    total_rows: int
    imported_deals: int
    created_organizations: int
    skipped_duplicates: int
    errors: list[str] = []


class VCardImportSummary(BaseModel):
    """Result of importing contacts from a vCard (.vcf) file."""

    total_cards: int
    imported_contacts: int
    created_organizations: int
    errors: list[str] = []
