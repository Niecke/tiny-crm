from __future__ import annotations

import json
import logging
import os
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.links import filter_by_link, load_scoped
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.document import (
    Document,
    document_contacts,
    document_deals,
    document_organizations,
)
from app.models.organization import Organization
from app.models.project import Project, project_documents
from app.schemas.document import DocumentRead, DocumentUpdate
from app.schemas.page import Page
from app.storage import delete_object, get_object_stream, put_object, put_object_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Everything a document can be filed against: the API field, the relationship
# it fills, the model its ids are checked against, and the join table plus its
# column for the list filter.
LINKS = (
    ("contact_ids", "contacts", Contact, document_contacts, "contact_id"),
    ("organization_ids", "organizations", Organization, document_organizations, "organization_id"),
    ("deal_ids", "deals", Deal, document_deals, "deal_id"),
    ("project_ids", "projects", Project, project_documents, "project_id"),
)


async def _apply_links(
    session: AsyncSession, doc: Document, values: dict[str, object], user_id: UUID
) -> None:
    """Replace whichever link lists the caller sent, leaving the rest alone."""
    for field, attribute, model, _table, _column in LINKS:
        if field not in values:
            continue
        ids = cast(list[UUID], values[field])
        setattr(doc, attribute, await load_scoped(session, model, ids, user_id))


_MAX_BYTES = 25 * 1024 * 1024  # 25 MB

_ALLOWED_FORMATS = {
    "application/pdf": "pdf",
    "text/markdown": "markdown",
    "text/plain": "txt",
    # browsers sometimes send these for .md files
    "text/x-markdown": "markdown",
}
_ALLOWED_EXTENSIONS = {".pdf": "pdf", ".md": "markdown", ".markdown": "markdown", ".txt": "txt"}


def _detect_format(filename: str, content_type: str) -> str | None:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _ALLOWED_FORMATS.get(content_type) or _ALLOWED_EXTENSIONS.get(ext)


def _checked_size(file: UploadFile) -> int:
    """Size of the upload, checked before any of it is pulled into memory.

    Starlette has already received the body — spooling it to a temp file past
    1 MB — and recorded its length, so this reads a counter rather than the
    file. Everything downstream streams, so an oversized upload is rejected
    without ever becoming a bytes object here."""
    size = file.size
    if size is None:  # no Content-Length from the client
        size = file.file.seek(0, os.SEEK_END)
        file.file.seek(0)
    if size > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")
    return size


async def _render_preview(file: UploadFile, fmt: str) -> bytes | None:
    """First page of a PDF as JPEG, or None for the other formats.

    pymupdf needs the whole document at once, so this is the single place the
    body is materialised — and only after the size check has passed."""
    if fmt != "pdf":
        return None
    await file.seek(0)
    return _generate_preview(await file.read())


def _generate_preview(data: bytes) -> bytes | None:
    try:
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        if not doc.page_count:
            return None
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
        # pymupdf is unannotated, so this would otherwise be an implicit Any.
        jpeg: bytes = pix.tobytes("jpeg")
        return jpeg
    except Exception:
        logger.exception("Failed to generate PDF preview")
        return None


def _content_type(fmt: str) -> str:
    return {"pdf": "application/pdf", "markdown": "text/markdown", "txt": "text/plain"}[fmt]


@router.get("/", response_model=Page[DocumentRead])
async def list_documents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = None,
    # "Everything filed against this record" — the question a document that
    # could only belong to a project could not answer.
    contact_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    deal_id: UUID | None = Query(default=None),
    project_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[DocumentRead]:
    q = select(Document).where(Document.user_id == user.id)
    if search:
        q = q.where(Document.title.ilike(f"%{search}%"))
    for target_id, (_field, _attr, _model, table, column) in zip(
        (contact_id, organization_id, deal_id, project_id), LINKS, strict=True
    ):
        if target_id is not None:
            q = filter_by_link(q, table, "document_id", column, target_id)
    total = await count_rows(session, q)
    result = await session.execute(
        q.order_by(Document.created_at.desc(), Document.id.asc()).offset(skip).limit(limit)
    )
    return Page[DocumentRead](
        items=[DocumentRead.model_validate(d) for d in result.scalars().all()],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/", response_model=DocumentRead, status_code=201)
async def upload_document(
    file: UploadFile,
    title: str = Form(...),
    description: str | None = Form(default=None),
    tags: str = Form(default="[]"),
    # JSON arrays in form fields, like `tags` — multipart has no native list
    # type, and attaching at upload time is the whole point: a contract is
    # filed against its deal as it arrives, not in a second step.
    contact_ids: str = Form(default="[]"),
    organization_ids: str = Form(default="[]"),
    deal_ids: str = Form(default="[]"),
    project_ids: str = Form(default="[]"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Document:
    size = _checked_size(file)

    fmt = _detect_format(file.filename or "", file.content_type or "")
    if fmt is None:
        raise HTTPException(status_code=422, detail="Unsupported file type — use pdf, md, or txt")

    parsed_tags: list[str] = json.loads(tags) if tags else []
    try:
        links = {
            field: [UUID(i) for i in json.loads(raw or "[]")]
            for field, raw in (
                ("contact_ids", contact_ids),
                ("organization_ids", organization_ids),
                ("deal_ids", deal_ids),
                ("project_ids", project_ids),
            )
        }
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=f"Malformed link list: {error}") from error

    # Resolved *before* anything reaches S3: a bad or someone else's id has to
    # fail while the only cost is a rejected request, not after the object is
    # already in the bucket with no row to ever delete it.
    linked = {
        attribute: await load_scoped(session, model, links[field], user.id)
        for field, attribute, model, _table, _column in LINKS
    }

    doc_id = uuid4()
    key = f"{user.id}/{doc_id}"

    await file.seek(0)
    await put_object_stream(key, file.file, _content_type(fmt))

    preview_image = await _render_preview(file, fmt)
    preview_key = f"{key}_preview" if preview_image else None
    if preview_image and preview_key:
        await put_object(preview_key, preview_image, "image/jpeg")

    doc = Document(
        id=doc_id,
        user_id=user.id,
        title=title,
        description=description,
        tags=parsed_tags,
        format=fmt,
        size=size,
        storage_key=key,
        preview_key=preview_key,
        **linked,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Document:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> StreamingResponse:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    safe_title = doc.title.replace('"', "").replace("\\", "")
    ext = {"pdf": "pdf", "markdown": "md", "txt": "txt"}[doc.format]
    return StreamingResponse(
        get_object_stream(doc.storage_key),
        media_type=_content_type(doc.format),
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.{ext}"'},
    )


@router.get("/{document_id}/preview")
async def get_document_preview(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> StreamingResponse:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.preview_key:
        raise HTTPException(status_code=404, detail="No preview available")
    return StreamingResponse(get_object_stream(doc.preview_key), media_type="image/jpeg")


@router.put("/{document_id}/content", response_model=DocumentRead)
async def replace_document_content(
    document_id: UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Document:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    size = _checked_size(file)

    fmt = _detect_format(file.filename or "", file.content_type or "")
    if fmt is None:
        raise HTTPException(status_code=422, detail="Unsupported file type — use pdf, md, or txt")

    # Put under the same key — versioned bucket keeps the old version
    await file.seek(0)
    await put_object_stream(doc.storage_key, file.file, _content_type(fmt))

    preview_image = await _render_preview(file, fmt)
    if preview_image:
        preview_key = f"{doc.storage_key}_preview"
        await put_object(preview_key, preview_image, "image/jpeg")
        doc.preview_key = preview_key
    else:
        doc.preview_key = None

    doc.format = fmt
    doc.size = size
    await session.commit()
    await session.refresh(doc)
    return doc


@router.patch("/{document_id}", response_model=DocumentRead)
async def update_document(
    document_id: UUID,
    body: DocumentUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Document:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    updates = body.model_dump(exclude_unset=True)
    await _apply_links(session, doc, updates, user.id)
    for field, value in updates.items():
        # The link lists are handled above; setattr would assign raw ids.
        if not field.endswith("_ids"):
            setattr(doc, field, value)
    await session.commit()
    await session.refresh(doc)
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await delete_object(doc.storage_key)
    if doc.preview_key:
        await delete_object(doc.preview_key)
    await session.delete(doc)
    await session.commit()
