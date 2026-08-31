from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_active_user
from app.auth.users import User
from app.db import count_rows, get_session
from app.models.project import project_tasks
from app.models.task import Task
from app.recurrence import RECURRENCE_RULES, RecurrenceRule, next_due_date
from app.schemas.page import Page
from app.schemas.task import (
    TaskCompletionRead,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    validate_recurrence,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _spawn_next_occurrence(session: AsyncSession, task: Task) -> Task | None:
    """Create the instance that follows `task` being completed, if there is one.

    The completed row is left alone — history is the point. Returns None when
    the task does not recur, when the series has passed `recurrence_until`, or
    when this row already has a successor (ticking a task done, undone and done
    again must not fork the series).
    """
    if task.due_date is None or task.recurrence_rule not in RECURRENCE_RULES:
        return None

    already_spawned = await session.scalar(
        select(Task.id).where(Task.recurrence_parent_id == task.id).limit(1)
    )
    if already_spawned is not None:
        return None

    due_date = next_due_date(
        task.due_date,
        cast(RecurrenceRule, task.recurrence_rule),
        task.recurrence_interval,
        completed_at=datetime.now(UTC),
        until=task.recurrence_until,
    )
    if due_date is None:
        return None

    successor = Task(
        user_id=task.user_id,
        title=task.title,
        description=task.description,
        due_date=due_date,
        priority=task.priority,
        tags=list(task.tags),
        done=False,
        recurrence_rule=task.recurrence_rule,
        recurrence_interval=task.recurrence_interval,
        recurrence_until=task.recurrence_until,
        recurrence_parent_id=task.id,
    )
    session.add(successor)
    # The link rows below reference the new id, so the row has to exist first.
    await session.flush()

    project_ids = (
        (
            await session.execute(
                select(project_tasks.c.project_id).where(project_tasks.c.task_id == task.id)
            )
        )
        .scalars()
        .all()
    )
    if project_ids:
        # A recurring task that belongs to a project keeps belonging to it.
        await session.execute(
            insert(project_tasks),
            [{"project_id": p, "task_id": successor.id} for p in project_ids],
        )
    return successor


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


@router.patch("/{task_id}", response_model=TaskCompletionRead)
async def update_task(
    task_id: UUID,
    body: TaskUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_active_user),
) -> TaskCompletionRead:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = body.model_dump(exclude_unset=True)
    # The recurrence fields have to hold together across the merge, not just
    # within the patch: clearing the due date of a repeating task, or adding a
    # rule to a task that has none, both leave nothing to repeat from.
    try:
        validate_recurrence(
            recurrence_rule=updates.get("recurrence_rule", task.recurrence_rule),
            recurrence_until=updates.get("recurrence_until", task.recurrence_until),
            due_date=updates.get("due_date", task.due_date),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    was_done = task.done
    for field, value in updates.items():
        setattr(task, field, value)

    successor = None
    if task.done and not was_done:
        successor = await _spawn_next_occurrence(session, task)

    await session.commit()
    await session.refresh(task)
    completed = TaskCompletionRead.model_validate(task)
    if successor is not None:
        await session.refresh(successor)
        completed.next_occurrence = TaskRead.model_validate(successor)
    return completed


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
