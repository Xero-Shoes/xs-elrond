"""
Finance spoke handler.
Called by cycle.py for tasks with spoke="finance".
Phase 1: skeleton only. Subagent implementations come in Phase 2.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def handle(task: dict, engine: "PolicyEngine") -> dict:
    """
    Dispatch a finance task to the appropriate subagent.
    Returns a result dict consumed by cycle.py.
    """
    task_type = task.get("type")
    task_id = str(task["_id"])

    logger.info(f"Finance handler: task={task_id} type={task_type}")

    # Phase 2 will route to real subagents:
    #   "pipeline"  → categorize_wholesale_orders → validate → invoice
    #   "review"    → generate_artifact
    #   "analysis"  → fetch_reconciliation_gap
    return {
        "summary": f"Finance task {task_id} ({task_type}): handler not yet implemented",
        "spoke": "finance",
        "skipped": True,
    }
