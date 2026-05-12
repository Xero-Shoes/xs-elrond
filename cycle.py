"""
Elrond execution cycle.
Entry point for each CCR run. Reads pending tasks, processes them in priority
order, and writes results back to MongoDB.

Usage (CCR prompt):
    python3 -m elrond.cycle
Or directly:
    python3 cycle.py
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from bson import ObjectId

from mongo.client import get_collection, ELROND_TASKS, ELROND_POLICY, ELROND_AUDIT_LOG, STRIDER_INBOX
from policy.engine import PolicyEngine
from context_tracker import ContextTracker

logger = logging.getLogger(__name__)

# Statuses Elrond acts on
ACTIONABLE_STATUSES = ["pending", "in_progress", "blocked", "waiting_human"]


def run_cycle(context_tracker: ContextTracker | None = None) -> dict:
    """
    Main execution loop. Returns a summary dict for the audit log / digest.

    context_tracker: optional — tracks context window usage for handoff.
    """
    tracker = context_tracker or ContextTracker()
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "tasks_processed": 0,
        "tasks_completed": 0,
        "tasks_blocked": 0,
        "humans_contacted": 0,
        "decisions_made": 0,
        "handoff_triggered": False,
        "errors": [],
    }

    tasks = _load_active_tasks()
    logger.info(f"Cycle start: {len(tasks)} active tasks")

    for task in tasks:
        if tracker.should_handoff():
            logger.warning("Context handoff threshold reached — writing snapshot")
            _write_handoff_snapshot(task["_id"], tasks, summary)
            summary["handoff_triggered"] = True
            break

        try:
            result = _process_task(task, tracker, summary)
            summary["tasks_processed"] += 1
            if result.get("completed"):
                summary["tasks_completed"] += 1
            if result.get("blocked"):
                summary["tasks_blocked"] += 1
            if result.get("human_contacted"):
                summary["humans_contacted"] += 1
            if result.get("decisions_made"):
                summary["decisions_made"] += result["decisions_made"]
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Error processing task {task['_id']}: {exc}")
            summary["errors"].append({"task_id": str(task["_id"]), "error": str(exc)})

    summary["ended_at"] = datetime.now(timezone.utc).isoformat()
    return summary


def _load_active_tasks() -> list[dict]:
    """Load all actionable tasks ordered by priority then age."""
    coll = get_collection(ELROND_TASKS)
    return list(
        coll.find({"status": {"$in": ACTIONABLE_STATUSES}})
        .sort([("priority", 1), ("created_at", 1)])
    )


def _process_task(task: dict, tracker: ContextTracker, summary: dict) -> dict:
    """
    Process a single task. Routes to the appropriate spoke handler.
    Returns a result dict indicating what happened.
    """
    task_id: ObjectId = task["_id"]
    spoke: str = task.get("spoke", "unknown")

    # 1. Check for new human input — unblock waiting tasks
    if task["status"] == "waiting_human":
        new_input = _check_for_human_input(task)
        if not new_input:
            logger.debug(f"Task {task_id}: still waiting for human input")
            return {"waiting": True}
        # Resume — fall through to normal processing

    # 2. Load policy for this spoke
    engine = PolicyEngine(spoke)
    if not engine.policy:
        logger.warning(f"Task {task_id}: no active policy for spoke '{spoke}' — skipping")
        return {"skipped": True}

    # 3. Dispatch to spoke handler
    spoke_result = _dispatch_to_spoke(task, engine)

    # 4. Write audit event
    _audit(task_id, spoke_result)

    return spoke_result


def _check_for_human_input(task: dict) -> dict | None:
    """Check strider_inbox for unprocessed input linked to this task."""
    coll = get_collection(STRIDER_INBOX)
    return coll.find_one({
        "linked_task_id": task["_id"],
        "processed_by_elrond": False,
    })


def _dispatch_to_spoke(task: dict, engine: "PolicyEngine") -> dict:
    """Route task to the correct spoke handler."""
    spoke = task.get("spoke", "unknown")

    if spoke == "finance":
        from spokes.finance.handler import handle
        return handle(task, engine)
    elif spoke == "discovery":
        from spokes.discovery.handler import handle
        return handle(task, engine)
    elif spoke == "calendar":
        from spokes.cal.handler import handle
        return handle(task, engine)
    else:
        logger.error(f"Unknown spoke: {spoke}")
        return {"error": f"unknown spoke: {spoke}"}


def _audit(task_id: ObjectId, result: dict) -> None:
    """Write a brief audit entry for the cycle step."""
    coll = get_collection(ELROND_AUDIT_LOG)
    coll.insert_one({
        "task_id": task_id,
        "event_type": "decision_made",
        "actor": "elrond",
        "subagent": result.get("subagent"),
        "summary": result.get("summary", "Cycle step processed"),
        "detail": result,
        "context_pct": None,
        "created_at": datetime.now(timezone.utc),
    })


def _write_handoff_snapshot(
    current_task_id: ObjectId,
    remaining_tasks: list[dict],
    partial_summary: dict,
) -> None:
    """Write context handoff document so next session can resume."""
    from mongo.client import get_db
    db = get_db()
    db["elrond_context_handoffs"].insert_one({
        "type": "context_handoff",
        "current_task_id": current_task_id,
        "remaining_task_ids": [t["_id"] for t in remaining_tasks],
        "partial_summary": partial_summary,
        "resume_instructions": (
            "Resume from the task listed in current_task_id. "
            "All tasks in remaining_task_ids are still pending. "
            "Check elrond_tasks for current status before acting."
        ),
        "created_at": datetime.now(timezone.utc),
    })


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    result = run_cycle()
    print(json.dumps(result, indent=2, default=str))
