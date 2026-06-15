from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import get_session
from app.models.contact import Contact
from app.models.document import Document
from app.models.project import Project
from app.models.task import Task
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_read(p: Project) -> ProjectRead:
    return ProjectRead(
        id=p.id,
        name=p.name,
        description=p.description,
        start_date=p.start_date,
        end_date=p.end_date,
        contact_ids=[c.id for c in p.contacts],
        task_ids=[t.id for t in p.tasks],
        document_ids=[d.id for d in p.documents],
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


async def _load_scoped[T](
    session: AsyncSession, model: type[T], ids: list[UUID], user_id: UUID
) -> list:
    """Fetch the given ids of `model` that belong to user_id. 404 on any miss."""
    if not ids:
        return []
    result = await session.execute(
        select(model).where(model.id.in_(ids), model.user_id == user_id)  # type: ignore[attr-defined]
    )
    found = list(result.scalars().all())
    if len(found) != len(set(ids)):
        raise HTTPException(status_code=404, detail=f"Unknown {model.__name__} id in link list")  # type: ignore[attr-defined]
    return found


@router.get("/", response_model=list[ProjectRead])
async def list_projects(
    skip: int = 0,
    limit: int = 200,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> list[ProjectRead]:
    query = select(Project).where(Project.user_id == user.id)
    if search:
        query = query.where(Project.name.ilike(f"%{search}%"))
    result = await session.execute(
        query.order_by(Project.start_date.desc()).offset(skip).limit(limit)
    )
    return [_to_read(p) for p in result.scalars().all()]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> ProjectRead:
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return _to_read(project)


@router.post("/", response_model=ProjectRead, status_code=201)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> ProjectRead:
    data = body.model_dump(exclude={"contact_ids", "task_ids", "document_ids"})
    project = Project(**data, user_id=user.id)
    project.contacts = await _load_scoped(session, Contact, body.contact_ids, user.id)
    project.tasks = await _load_scoped(session, Task, body.task_ids, user.id)
    project.documents = await _load_scoped(session, Document, body.document_ids, user.id)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _to_read(project)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> ProjectRead:
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "contact_ids":
            project.contacts = await _load_scoped(session, Contact, value, user.id)
        elif field == "task_ids":
            project.tasks = await _load_scoped(session, Task, value, user.id)
        elif field == "document_ids":
            project.documents = await _load_scoped(session, Document, value, user.id)
        else:
            setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return _to_read(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    await session.delete(project)
    await session.commit()
