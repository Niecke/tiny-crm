"""vCard 3.0 generation and ingestion for Contacts.

Supports RFC 2426 / RFC 6350 vCard formatting with proper line unfolding,
escaping/unescaping, multi-contact streams, and organization resolution.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import live
from app.models.contact import Contact
from app.models.organization import Organization
from app.schemas.import_export import VCardImportSummary

if TYPE_CHECKING:
    from app.auth.users import User

# Common country name mappings to ISO 3166-1 alpha-2
_COUNTRY_MAP: dict[str, str] = {
    "austria": "AT",
    "österreich": "AT",
    "germany": "DE",
    "deutschland": "DE",
    "switzerland": "CH",
    "schweiz": "CH",
    "united states": "US",
    "usa": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "liechtenstein": "LI",
    "italy": "IT",
    "italien": "IT",
    "france": "FR",
    "frankreich": "FR",
    "netherlands": "NL",
    "niederlande": "NL",
    "belgium": "BE",
    "belgien": "BE",
    "spain": "ES",
    "spanien": "ES",
    "portugal": "PT",
    "canada": "CA",
    "kanada": "CA",
    "australia": "AU",
    "australien": "AU",
    "new zealand": "NZ",
    "ireland": "IE",
    "irland": "IE",
    "poland": "PL",
    "polen": "PL",
    "czech republic": "CZ",
    "czechia": "CZ",
    "tschechien": "CZ",
    "slovakia": "SK",
    "slowakei": "SK",
    "slovenia": "SI",
    "slowenien": "SI",
    "hungary": "HU",
    "ungarn": "HU",
    "croatia": "HR",
    "kroatien": "HR",
    "sweden": "SE",
    "schweden": "SE",
    "norway": "NO",
    "norwegen": "NO",
    "denmark": "DK",
    "dänemark": "DK",
    "finland": "FI",
    "finnland": "FI",
    "greece": "GR",
    "griechenland": "GR",
    "luxembourg": "LU",
    "luxemburg": "LU",
    "romania": "RO",
    "rumänien": "RO",
    "bulgaria": "BG",
    "bulgarien": "BG",
    "cyprus": "CY",
    "zypern": "CY",
    "malta": "MT",
    "estonia": "EE",
    "estland": "EE",
    "latvia": "LV",
    "lettland": "LV",
    "lithuania": "LT",
    "litauen": "LT",
    "japan": "JP",
    "china": "CN",
    "india": "IN",
    "indien": "IN",
    "brazil": "BR",
    "brasilien": "BR",
    "mexico": "MX",
    "mexiko": "MX",
    "singapore": "SG",
    "singapur": "SG",
}


def _escape(text: str) -> str:
    """Escape special characters per vCard specification."""
    return (
        text.replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _unescape(text: str) -> str:
    """Unescape vCard escaped characters."""
    result: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        if text[i] == "\\" and i + 1 < length:
            next_char = text[i + 1]
            if next_char in ("n", "N"):
                result.append("\n")
                i += 2
                continue
            if next_char in (",", ";", "\\"):
                result.append(next_char)
                i += 2
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


def _fold_line(line: str) -> str:
    """Fold lines exceeding 75 characters per RFC 2426 / 6350."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts: list[str] = []
    current = ""
    for char in line:
        char_bytes = len((current + char).encode("utf-8"))
        if char_bytes > 75 and current:
            parts.append(current)
            current = " " + char
        else:
            current += char
    if current:
        parts.append(current)
    return "\r\n".join(parts)


def contact_to_vcard(contact: Contact) -> str:
    """Format a single Contact model into a standard vCard 3.0 string."""
    lines: list[str] = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{_escape(contact.name)}",
    ]

    # Name parts (Family;Given;Additional;Prefix;Suffix)
    name_parts = contact.name.strip().split(None, 1)
    if len(name_parts) == 2:
        given, family = name_parts[0], name_parts[1]
        lines.append(f"N:{_escape(family)};{_escape(given)};;;")
    else:
        lines.append(f"N:{_escape(contact.name)};;;;")

    if contact.organization_name:
        lines.append(f"ORG:{_escape(contact.organization_name)}")

    if contact.job_title:
        lines.append(f"TITLE:{_escape(contact.job_title)}")

    if contact.email:
        lines.append(f"EMAIL;TYPE=INTERNET,PREF:{_escape(contact.email)}")

    if contact.email_secondary:
        lines.append(f"EMAIL;TYPE=INTERNET:{_escape(contact.email_secondary)}")

    if contact.phone:
        lines.append(f"TEL;TYPE=VOICE,PREF:{_escape(contact.phone)}")

    if contact.phone_secondary:
        lines.append(f"TEL;TYPE=CELL:{_escape(contact.phone_secondary)}")

    if contact.website:
        lines.append(f"URL:{_escape(contact.website)}")

    # Address (pobox;extended;street;locality;region;postal_code;country)
    if any([contact.street, contact.city, contact.postal_code, contact.country]):
        street = _escape(contact.street or "")
        city = _escape(contact.city or "")
        postal = _escape(contact.postal_code or "")
        country = _escape(contact.country or "")
        lines.append(f"ADR;TYPE=WORK:;;{street};{city};;{postal};{country}")

    if contact.birthday:
        lines.append(f"BDAY:{contact.birthday.isoformat()}")

    if contact.tags:
        escaped_tags = ",".join(_escape(tag) for tag in contact.tags)
        lines.append(f"CATEGORIES:{escaped_tags}")

    if contact.notes:
        lines.append(f"NOTE:{_escape(contact.notes)}")

    lines.append("END:VCARD")

    folded = [_fold_line(line) for line in lines]
    return "\r\n".join(folded) + "\r\n"


def contacts_to_vcards(contacts: Sequence[Contact]) -> str:
    """Format multiple contacts into a multi-vCard stream."""
    return "".join(contact_to_vcard(contact) for contact in contacts)


@dataclass
class ParsedVCard:
    name: str = ""
    job_title: str | None = None
    organization_name: str | None = None
    email: str | None = None
    email_secondary: str | None = None
    phone: str | None = None
    phone_secondary: str | None = None
    website: str | None = None
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None
    birthday: date | None = None
    notes: str | None = None
    tags: list[str] = field(default_factory=list)


def _unfold_lines(text: str) -> list[str]:
    """Unfold lines per RFC: remove newline followed immediately by whitespace."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    unfolded = re.sub(r"\n[ \t]", "", normalized)
    return [line.strip() for line in unfolded.split("\n") if line.strip()]


def _split_unescaped(text: str, delimiter: str = ";") -> list[str]:
    """Split string on unescaped delimiter."""
    parts: list[str] = []
    current: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        if text[i] == "\\" and i + 1 < length:
            current.append(text[i : i + 2])
            i += 2
            continue
        if text[i] == delimiter:
            parts.append("".join(current))
            current = []
            i += 1
            continue
        current.append(text[i])
        i += 1
    parts.append("".join(current))
    return parts


def _normalize_country(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper()
    lower = cleaned.lower()
    return _COUNTRY_MAP.get(lower)


def parse_vcards(text: str) -> list[ParsedVCard]:
    """Parse single or multi-vCard text into a list of ParsedVCard dataclasses."""
    lines = _unfold_lines(text)
    results: list[ParsedVCard] = []
    current_card: ParsedVCard | None = None
    n_field_fallback: str | None = None

    for line in lines:
        if line.upper() == "BEGIN:VCARD":
            current_card = ParsedVCard()
            n_field_fallback = None
            continue

        if line.upper() == "END:VCARD":
            if current_card is not None:
                if not current_card.name and n_field_fallback:
                    current_card.name = n_field_fallback
                if current_card.name:
                    results.append(current_card)
            current_card = None
            n_field_fallback = None
            continue

        if current_card is None:
            continue

        if ":" not in line:
            continue

        prop_header, prop_val = line.split(":", 1)
        prop_parts = prop_header.upper().split(";")
        prop_name = prop_parts[0]
        params = prop_parts[1:] if len(prop_parts) > 1 else []

        if prop_name == "FN":
            current_card.name = _unescape(prop_val).strip()

        elif prop_name == "N":
            # N:Family;Given;Additional;Prefix;Suffix
            n_parts = [_unescape(p).strip() for p in _split_unescaped(prop_val, ";")]
            family = n_parts[0] if len(n_parts) > 0 else ""
            given = n_parts[1] if len(n_parts) > 1 else ""
            name = f"{given} {family}".strip()
            if name:
                n_field_fallback = name

        elif prop_name == "ORG":
            # ORG can contain sub-units separated by semicolon
            org_parts = [_unescape(p).strip() for p in _split_unescaped(prop_val, ";")]
            if org_parts and org_parts[0]:
                current_card.organization_name = org_parts[0]

        elif prop_name == "TITLE":
            current_card.job_title = _unescape(prop_val).strip() or None

        elif prop_name == "EMAIL":
            val = _unescape(prop_val).strip()
            if val:
                if current_card.email is None:
                    current_card.email = val
                elif current_card.email_secondary is None and val != current_card.email:
                    current_card.email_secondary = val

        elif prop_name == "TEL":
            val = _unescape(prop_val).strip()
            if val:
                is_cell = any("CELL" in p for p in params)
                if current_card.phone is None and not is_cell:
                    current_card.phone = val
                elif current_card.phone_secondary is None:
                    current_card.phone_secondary = val
                elif current_card.phone is None:
                    current_card.phone = val

        elif prop_name == "URL":
            current_card.website = _unescape(prop_val).strip() or None

        elif prop_name == "ADR":
            adr_parts = [_unescape(p).strip() for p in _split_unescaped(prop_val, ";")]
            # pobox;ext;street;city;region;postal;country
            if len(adr_parts) > 2 and adr_parts[2]:
                current_card.street = adr_parts[2]
            if len(adr_parts) > 3 and adr_parts[3]:
                current_card.city = adr_parts[3]
            if len(adr_parts) > 5 and adr_parts[5]:
                current_card.postal_code = adr_parts[5]
            if len(adr_parts) > 6 and adr_parts[6]:
                norm_country = _normalize_country(adr_parts[6])
                if norm_country:
                    current_card.country = norm_country
                else:
                    raw_country = adr_parts[6].strip()
                    if current_card.city:
                        current_card.city = f"{current_card.city}, {raw_country}"
                    else:
                        current_card.city = raw_country

        elif prop_name == "BDAY":
            val = _unescape(prop_val).strip()
            try:
                # ISO YYYY-MM-DD or YYYYMMDD
                clean_date = val.replace("-", "")
                if len(clean_date) == 8 and clean_date.isdigit():
                    current_card.birthday = date(
                        int(clean_date[:4]), int(clean_date[4:6]), int(clean_date[6:])
                    )
            except ValueError:
                pass

        elif prop_name == "NOTE":
            unescaped_note = _unescape(prop_val).strip()
            if unescaped_note:
                current_card.notes = unescaped_note

        elif prop_name == "CATEGORIES":
            cat_parts = [_unescape(p).strip() for p in _split_unescaped(prop_val, ",")]
            current_card.tags.extend([p for p in cat_parts if p])

    return results


async def import_vcards(
    session: AsyncSession,
    user: User,
    text: str,
) -> VCardImportSummary:
    """Ingest vCard text into Contact and Organization records for `user`."""
    parsed = parse_vcards(text)
    if not parsed:
        return VCardImportSummary(
            total_cards=0,
            imported_contacts=0,
            created_organizations=0,
            errors=["No valid vCards found in file."],
        )

    # Cache user organizations to avoid redundant queries during bulk import
    org_query = select(Organization).where(Organization.user_id == user.id, live(Organization))
    org_res = await session.execute(org_query)
    existing_orgs = {org.name.lower(): org for org in org_res.scalars().all()}

    imported_contacts = 0
    created_organizations = 0
    errors: list[str] = []

    for item in parsed:
        if not item.name:
            continue

        org_id = None
        if item.organization_name:
            norm_org = item.organization_name.strip().lower()
            if norm_org in existing_orgs:
                org_id = existing_orgs[norm_org].id
            else:
                new_org = Organization(
                    name=item.organization_name.strip(),
                    user_id=user.id,
                )
                session.add(new_org)
                await session.flush()
                existing_orgs[norm_org] = new_org
                org_id = new_org.id
                created_organizations += 1

        contact = Contact(
            name=item.name,
            job_title=item.job_title,
            organization_id=org_id,
            email=item.email,
            email_secondary=item.email_secondary,
            phone=item.phone,
            phone_secondary=item.phone_secondary,
            website=item.website,
            street=item.street,
            postal_code=item.postal_code,
            city=item.city,
            country=item.country,
            birthday=item.birthday,
            notes=item.notes,
            tags=list(dict.fromkeys(item.tags)),  # deduplicate preserving order
            user_id=user.id,
        )
        session.add(contact)
        imported_contacts += 1

    await session.commit()

    return VCardImportSummary(
        total_cards=len(parsed),
        imported_contacts=imported_contacts,
        created_organizations=created_organizations,
        errors=errors,
    )
