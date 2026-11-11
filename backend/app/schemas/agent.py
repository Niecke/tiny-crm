"""The agent API's responses (#320): compact on purpose.

An agent pays for every token it reads, so these are not the read models:
nothing that is null or empty is sent (the routes use `response_model_exclude_none`
and set an empty list to None), no nested full records, notes cut to an excerpt.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

HitType = Literal["contact", "organization", "deal"]


class AgentHit(BaseModel):
    type: HitType
    id: UUID
    title: str
    subtitle: str | None = None


class AgentSearch(BaseModel):
    q: str
    hits: list[AgentHit]


class AgentInteraction(BaseModel):
    id: UUID
    kind: str
    subject: str
    occurred_at: datetime
    done: bool
    notes_excerpt: str | None = None


class AgentRef(BaseModel):
    id: UUID
    name: str


class AgentContact(BaseModel):
    id: UUID
    name: str
    archived: bool | None = None
    job_title: str | None = None
    organization: AgentRef | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    country: str | None = None
    lifecycle_status: str | None = None
    relation_type: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    recent_interactions: list[AgentInteraction] | None = None


class AgentOrgContact(BaseModel):
    id: UUID
    name: str
    job_title: str | None = None


class AgentOrgDeal(BaseModel):
    id: UUID
    title: str
    stage: str


class AgentOrganization(BaseModel):
    id: UUID
    name: str
    archived: bool | None = None
    domain: str | None = None
    email: str | None = None
    phone: str | None = None
    industry: str | None = None
    notes: str | None = None
    contacts: list[AgentOrgContact] | None = None
    open_deals: list[AgentOrgDeal] | None = None
    recent_interactions: list[AgentInteraction] | None = None


class AgentDeal(BaseModel):
    id: UUID
    title: str
    stage: str
    currency: str
    days_in_stage: int
    expected_value: Decimal | None = None
    probability: int | None = None
    expected_close_date: date | None = None
    contact_name: str | None = None
    organization_name: str | None = None


class AgentPipeline(BaseModel):
    deals: list[AgentDeal]
    # Sum of expected_value per currency, over every open deal — not only the
    # rows listed. Adding two currencies would be a lie.
    totals: dict[str, Decimal]
    truncated: bool | None = None


class AgentTask(BaseModel):
    id: UUID
    title: str
    priority: int
    due_date: datetime | None = None
    days_late: int | None = None
    contact_name: str | None = None
    deal_title: str | None = None


class AgentTasks(BaseModel):
    date: date
    timezone: str
    overdue: list[AgentTask]
    today: list[AgentTask]
