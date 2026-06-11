from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import get_session
from app.models.document import Document
from app.schemas.document import DocumentRead, DocumentUpdate
from app.storage import delete_object, get_object_stream, put_object

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

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


def _generate_preview(data: bytes, fmt: str) -> bytes | None:
    if fmt != "pdf":
        return None
    try:
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        if not doc.page_count:
            return None
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
        return pix.tobytes("jpeg")
    except Exception:
        logger.exception("Failed to generate PDF preview")
        return None


def _content_type(fmt: str) -> str:
    return {"pdf": "application/pdf", "markdown": "text/markdown", "txt": "text/plain"}[fmt]


@router.get("/", response_model=list[DocumentRead])
async def list_documents(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> list[Document]:
    q = select(Document).where(Document.user_id == user.id)
    if search:
        q = q.where(Document.title.ilike(f"%{search}%"))
    result = await session.execute(q.offset(skip).limit(limit))
    return list(result.scalars().all())


@router.post("/", response_model=DocumentRead, status_code=201)
async def upload_document(
    file: UploadFile,
    title: str = Form(...),
    description: str | None = Form(default=None),
    tags: str = Form(default="[]"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Document:
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

    fmt = _detect_format(file.filename or "", file.content_type or "")
    if fmt is None:
        raise HTTPException(status_code=422, detail="Unsupported file type — use pdf, md, or txt")

    parsed_tags: list[str] = json.loads(tags) if tags else []
    doc_id = uuid4()
    key = f"{user.id}/{doc_id}"
    preview_image = _generate_preview(data, fmt)
    preview_key = f"{key}_preview" if preview_image else None

    await put_object(key, data, _content_type(fmt))
    if preview_image and preview_key:
        await put_object(preview_key, preview_image, "image/jpeg")

    doc = Document(
        id=doc_id,
        user_id=user.id,
        title=title,
        description=description,
        tags=parsed_tags,
        format=fmt,
        size=len(data),
        storage_key=key,
        preview_key=preview_key,
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

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

    fmt = _detect_format(file.filename or "", file.content_type or "")
    if fmt is None:
        raise HTTPException(status_code=422, detail="Unsupported file type — use pdf, md, or txt")

    # Put under the same key — versioned bucket keeps the old version
    await put_object(doc.storage_key, data, _content_type(fmt))

    preview_image = _generate_preview(data, fmt)
    if preview_image:
        preview_key = f"{doc.storage_key}_preview"
        await put_object(preview_key, preview_image, "image/jpeg")
        doc.preview_key = preview_key
    else:
        doc.preview_key = None

    doc.format = fmt
    doc.size = len(data)
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
    for field, value in body.model_dump(exclude_unset=True).items():
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
