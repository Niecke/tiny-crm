"""vCard 3.0 generation and ingestion for Contacts.

Supports RFC 2426 / RFC 6350 vCard formatting with proper line unfolding,
escaping/unescaping, multi-contact streams, and organization resolution.
Reading is more forgiving than writing: what phones and address books export
is as often vCard 2.1 (quoted-printable values) or grouped (`item1.EMAIL`) as
it is the 3.0 written here.
"""

from __future__ import annotations

import quopri
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.archive import live
from app.db import one_at_a_time
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


def _is_quoted_printable(header: str) -> bool:
    return "QUOTED-PRINTABLE" in header.upper()


def _unfold_lines(text: str) -> list[str]:
    """Unfold lines per RFC: remove newline followed immediately by whitespace.

    A quoted-printable value (vCard 2.1) continues differently: a trailing `=`
    is a soft line break and the next line carries on from its first character,
    so those are rejoined here as well.
    """
    lines: list[str] = []
    soft_break = False
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if soft_break:
            lines[-1] = lines[-1].rstrip()[:-1] + raw_line
        elif lines and raw_line[:1] in (" ", "\t"):
            lines[-1] += raw_line[1:]
        elif raw_line.strip():
            lines.append(raw_line)
        else:
            continue
        soft_break = lines[-1].rstrip().endswith("=") and _is_quoted_printable(
            lines[-1].split(":", 1)[0]
        )
    return [line.strip() for line in lines if line.strip()]


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


def _qp_charset(params: list[str]) -> str | None:
    """The charset of a quoted-printable value, or None for a plain one.

    vCard 2.1 only — what Android still exports by default:
    `FN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:J=C3=BCrgen`.
    """
    if not any(_is_quoted_printable(p) for p in params):
        return None
    for param in params:
        if param.startswith("CHARSET="):
            return param.removeprefix("CHARSET=")
    return "UTF-8"


def _text(raw: str, charset: str | None) -> str:
    """One value as it was meant: quoted-printable decoded if it is, then unescaped."""
    if charset is not None:
        decoded = quopri.decodestring(raw.encode("utf-8"))
        try:
            raw = decoded.decode(charset, errors="replace")
        except LookupError:  # a charset Python has never heard of
            raw = decoded.decode("utf-8", errors="replace")
    return _unescape(raw).strip()


def _parts(raw: str, delimiter: str, charset: str | None) -> list[str]:
    """A structured value's components. Split first: an encoded `;` is not a separator."""
    return [_text(part, charset) for part in _split_unescaped(raw, delimiter)]


def _is_preferred(params: list[str]) -> bool:
    """`TYPE=WORK,PREF` (3.0), a bare `PREF` (2.1) or `PREF=1` (4.0)."""
    return any("PREF" in param for param in params)


def _normalize_country(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    # The map first, so "UK" becomes GB rather than passing as a code of its own.
    mapped = _COUNTRY_MAP.get(cleaned.lower())
    if mapped:
        return mapped
    # ASCII only, like the schema's pattern: str.isalpha() is true of "日本",
    # which would be stored and then fail every read of the contact.
    if re.fullmatch(r"[A-Za-z]{2}", cleaned):
        return cleaned.upper()
    return None


def _pick_emails(emails: list[tuple[bool, str]]) -> tuple[str | None, str | None]:
    """Primary and secondary address: the preferred one first, then file order."""
    ordered = list(dict.fromkeys(address for _, address in sorted(emails, key=lambda e: not e[0])))
    first, second, *_ = [*ordered, None, None]
    return first, second


def _pick_phones(phones: list[tuple[bool, bool, str]]) -> tuple[str | None, str | None]:
    """Primary and secondary number from (preferred, is_cell, number) in file order.

    The preferred number is the primary one; without one it is the first that
    is not a mobile, which is how contact_to_vcard writes the pair out. Whatever
    comes next is the secondary — so a card with nothing but a mobile number
    keeps it there, and an exported contact reads back as it was.
    """
    primary = next((p for p in phones if p[0]), None) or next((p for p in phones if not p[1]), None)
    rest = [p[2] for p in phones if p is not primary]
    if primary is not None:
        return primary[2], rest[0] if rest else None
    return (rest[1] if len(rest) > 1 else None), (rest[0] if rest else None)


def parse_vcards(text: str) -> list[ParsedVCard]:
    """Parse single or multi-vCard text into a list of ParsedVCard dataclasses.

    A card with neither FN nor N comes back with an empty name rather than
    being dropped, so the caller can say that it was there.
    """
    lines = _unfold_lines(text)
    results: list[ParsedVCard] = []
    current_card: ParsedVCard | None = None
    n_field_fallback: str | None = None
    emails: list[tuple[bool, str]] = []
    phones: list[tuple[bool, bool, str]] = []
    # None until an address is taken, then whether that one was marked preferred.
    address_preferred: bool | None = None

    for line in lines:
        if line.upper() == "BEGIN:VCARD":
            current_card = ParsedVCard()
            n_field_fallback = None
            emails = []
            phones = []
            address_preferred = None
            continue

        if line.upper() == "END:VCARD":
            if current_card is not None:
                if not current_card.name and n_field_fallback:
                    current_card.name = n_field_fallback
                current_card.email, current_card.email_secondary = _pick_emails(emails)
                current_card.phone, current_card.phone_secondary = _pick_phones(phones)
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
        # `item1.EMAIL` is an EMAIL: the group prefix only ties properties
        # together (Apple and Google use it to hang a label on one).
        prop_name = prop_parts[0].rsplit(".", 1)[-1]
        params = prop_parts[1:]
        charset = _qp_charset(params)

        if prop_name == "FN":
            current_card.name = _text(prop_val, charset)

        elif prop_name == "N":
            # N:Family;Given;Additional;Prefix;Suffix
            n_parts = _parts(prop_val, ";", charset)
            family = n_parts[0] if len(n_parts) > 0 else ""
            given = n_parts[1] if len(n_parts) > 1 else ""
            name = f"{given} {family}".strip()
            if name:
                n_field_fallback = name

        elif prop_name == "ORG":
            # ORG can contain sub-units separated by semicolon
            org_parts = _parts(prop_val, ";", charset)
            if org_parts and org_parts[0]:
                current_card.organization_name = org_parts[0]

        elif prop_name == "TITLE":
            current_card.job_title = _text(prop_val, charset) or None

        elif prop_name == "EMAIL":
            val = _text(prop_val, charset)
            if val:
                emails.append((_is_preferred(params), val))

        elif prop_name == "TEL":
            val = _text(prop_val, charset)
            if val:
                is_cell = any("CELL" in p for p in params)
                phones.append((_is_preferred(params), is_cell, val))

        elif prop_name == "URL":
            current_card.website = _text(prop_val, charset) or None

        elif prop_name == "ADR":
            # pobox;ext;street;city;region;postal;country
            adr_parts = _parts(prop_val, ";", charset) + [""] * 7
            street, city, postal, raw_country = (
                adr_parts[2],
                adr_parts[3],
                adr_parts[5],
                adr_parts[6],
            )
            preferred = _is_preferred(params)
            # One address, taken whole: the first, unless a later one is marked
            # preferred. Filling the four fields from whichever ADR happens to
            # have each makes an address that exists nowhere.
            wanted = address_preferred is None or (preferred and not address_preferred)
            if wanted and any((street, city, postal, raw_country)):
                country = _normalize_country(raw_country)
                if raw_country and country is None:
                    # No code for it, and the column holds nothing else: kept
                    # on the city line rather than dropped.
                    city = f"{city}, {raw_country}" if city else raw_country
                current_card.street = street or None
                current_card.city = city or None
                current_card.postal_code = postal or None
                current_card.country = country
                address_preferred = preferred

        elif prop_name == "BDAY":
            val = _text(prop_val, charset)
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
            unescaped_note = _text(prop_val, charset)
            if unescaped_note:
                current_card.notes = unescaped_note

        elif prop_name == "CATEGORIES":
            current_card.tags.extend(p for p in _parts(prop_val, ",", charset) if p)

    return results


def _identities(name: str, *emails: str | None) -> set[tuple[str, str]]:
    """What a contact is recognised by on a re-import: its name with each address.

    Name alone would merge two people called the same; address alone would merge
    everyone behind one office@. A contact with no address is its name and
    nothing else, which only another one without an address can match.
    """
    key = name.strip().casefold()
    addresses = {e.strip().casefold() for e in emails if e and e.strip()}
    return {(key, address) for address in addresses} or {(key, "")}


async def import_vcards(
    session: AsyncSession,
    user: User,
    text: str,
) -> VCardImportSummary:
    """Ingest vCard text into Contact and Organization records for `user`.

    A card whose name and e-mail address already belong to a contact — live or
    archived, or earlier in the same file — is skipped, so sending the same
    file twice, or importing what was just exported, changes nothing.
    """
    parsed = parse_vcards(text)
    if not parsed:
        return VCardImportSummary(
            total_cards=0,
            imported_contacts=0,
            created_organizations=0,
            skipped_duplicates=0,
            errors=["No valid vCards found in file."],
        )

    # Two uploads of one file must not both find the contacts missing.
    await one_at_a_time(session, f"import:{user.id}")

    # Cache user organizations to avoid redundant queries during bulk import
    org_query = select(Organization).where(Organization.user_id == user.id, live(Organization))
    org_res = await session.execute(org_query)
    existing_orgs = {org.name.lower(): org for org in org_res.scalars().all()}

    # Archived contacts included: one that was put away is not to come back
    # as a second, live copy of itself.
    contact_res = await session.execute(
        select(Contact.name, Contact.email, Contact.email_secondary).where(
            Contact.user_id == user.id
        )
    )
    known: set[tuple[str, str]] = set()
    for name, email, email_secondary in contact_res.all():
        known |= _identities(name, email, email_secondary)

    imported_contacts = 0
    created_organizations = 0
    skipped_duplicates = 0
    errors: list[str] = []

    for card_number, item in enumerate(parsed, start=1):
        if not item.name:
            errors.append(f"Card {card_number}: no name (FN or N), skipped.")
            continue

        identities = _identities(item.name, item.email, item.email_secondary)
        if identities & known:
            skipped_duplicates += 1
            continue
        known |= identities

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
        skipped_duplicates=skipped_duplicates,
        errors=errors,
    )
