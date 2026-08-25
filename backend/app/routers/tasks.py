from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.models.task import Task
from app.schemas.page import Page
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/", response_model=Page[TaskRead])
async def list_tasks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = None,
    include_done: bool = False,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Page[TaskRead]:
    query = select(Task).where(Task.user_id == user.id)
    if not include_done:
        query = query.where(Task.done.is_(False))
    if search:
        query = query.where(Task.title.ilike(f"%{search}%"))
    total = await count_rows(session, query)
    # NULLS LAST so tasks without a due date sink to the bottom; client renders
    # overdue (due_date < now) red, and ascending order naturally floats them up.
    result = await session.execute(
        query.order_by(Task.due_date.asc().nulls_last(), Task.created.asc(), Task.id.asc())
        .offset(skip)
        .limit(limit)
    )
    return Page[TaskRead](
        items=[TaskRead.model_validate(t) for t in result.scalars().all()],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Task:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/", response_model=TaskRead, status_code=201)
async def create_task(
    body: TaskCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Task:
    task = Task(**body.model_dump(), user_id=user.id)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID,
    body: TaskUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> Task:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> None:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    await session.delete(task)
    await session.commit()
