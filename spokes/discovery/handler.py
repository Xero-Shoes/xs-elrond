"""
Discovery spoke handler.
Called by cycle.py for tasks with spoke="discovery".
Phase 1: skeleton only.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def handle(task: dict, engine: "PolicyEngine") -> dict:
    """
    Dispatch a discovery task to the appropriate subagent.
    """
    task_type = task.get("type")
    task_id = str(task["_id"])

    logger.info(f"Discovery handler: task={task_id} type={task_type}")

    # Phase 2 will route:
    #   "interview"  → send_interview_question → collect response → analyze
    #   "analysis"   → analyze_interview_transcript / run_cross_analysis
    return {
        "summary": f"Discovery task {task_id} ({task_type}): handler not yet implemented",
        "spoke": "discovery",
        "skipped": True,
    }
