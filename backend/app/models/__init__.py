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

from app.models.contact import Contact
from app.models.deal import Deal
from app.models.document import Document
from app.models.interaction import Interaction
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.watch import Watch, WatchCheck

__all__ = [
    "Contact",
    "Deal",
    "Document",
    "Interaction",
    "Organization",
    "Project",
    "Task",
    "Watch",
    "WatchCheck",
]
