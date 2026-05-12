"""
Calendar spoke handler.
Called by cycle.py for tasks with spoke="calendar".
Phase 1: skeleton only.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def handle(task: dict, engine: "PolicyEngine") -> dict:
    """
    Dispatch a calendar task to the appropriate subagent.
    """
    task_type = task.get("type")
    task_id = str(task["_id"])

    logger.info(f"Calendar handler: task={task_id} type={task_type}")

    # Phase 2 will route:
    #   "calendar_request" → find_availability → confirm slot → create event
    return {
        "summary": f"Calendar task {task_id} ({task_type}): handler not yet implemented",
        "spoke": "calendar",
        "skipped": True,
    }
