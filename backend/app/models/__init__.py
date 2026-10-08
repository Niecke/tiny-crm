"""Every mapped model, imported so the SQLAlchemy registry is complete.

Importing one model is not enough to use it. `Interaction.projects` names
`"Project"` as a string (a runtime import would be a cycle), and SQLAlchemy
resolves that name against the registry the first time any mapper is
configured — so a process that has imported `Interaction` but not `Project`
fails on its first query with "expression 'Project' failed to locate a name",
not at import time.

The API never hit this because `app/main.py` pulls in every router, and each
router imports its own model. Anything else that opens a session — a script
run from a CronJob, a one-off in a shell — has to import this package
instead, and gets the whole registry from one import.

*Adding a model file? Add it here*, and every entry point picks it up.
"""

# Attaches Deal.has_next_step, which needs Task and Interaction and so cannot
# live in deal.py. Imported for that side effect; see the module.
from app.audit import AuditEvent
from app.models import next_step  # noqa: F401
from app.models.capture import Capture
from app.models.contact import Contact
from app.models.deal import Deal, DealStageEvent
from app.models.document import Document
from app.models.interaction import Interaction
from app.models.organization import Organization
from app.models.project import Project

# Registers the search indexes on the tables above; see the module.
from app.models.search import SEARCHABLES
from app.models.task import Task
from app.models.watch import Watch, WatchCheck

__all__ = [
    "AuditEvent",
    "Capture",
    "Contact",
    "Deal",
    "DealStageEvent",
    "Document",
    "Interaction",
    "Organization",
    "Project",
    "SEARCHABLES",
    "Task",
    "Watch",
    "WatchCheck",
]
