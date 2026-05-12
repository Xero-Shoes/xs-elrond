"""
Cycle + policy engine smoke tests.
Requires live MongoDB (MONGO_URI in .env).
Run: pytest tests/test_cycle.py -v
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="session", autouse=True)
def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


# ── ContextTracker ────────────────────────────────────────────────────────────

def test_context_tracker_no_handoff():
    from context_tracker import ContextTracker
    t = ContextTracker(current_pct=0.10, threshold=0.45)
    assert not t.should_handoff()


def test_context_tracker_handoff():
    from context_tracker import ContextTracker
    t = ContextTracker(current_pct=0.50, threshold=0.45)
    assert t.should_handoff()


def test_context_tracker_set_pct():
    from context_tracker import ContextTracker
    t = ContextTracker()
    t.set_pct(0.46)
    assert t.should_handoff()


# ── PolicyEngine ──────────────────────────────────────────────────────────────

def test_policy_engine_finance():
    from policy.engine import PolicyEngine
    engine = PolicyEngine("finance")
    assert engine.policy is not None
    assert engine.can_act("run_phase_a")
    assert engine.can_act("query_mongodb")
    assert not engine.can_act("run_phase_c_production")
    assert engine.needs_stephan("run_phase_c_production")
    assert engine.needs_strider("request_missing_customer_mapping")


def test_policy_engine_discovery():
    from policy.engine import PolicyEngine
    engine = PolicyEngine("discovery")
    assert engine.policy is not None
    assert engine.can_act("analyze_interview_transcript")
    assert not engine.can_act("publish_sop")
    assert engine.needs_stephan("publish_sop")


def test_policy_engine_calendar():
    from policy.engine import PolicyEngine
    engine = PolicyEngine("calendar")
    assert engine.policy is not None
    assert engine.can_act("find_availability")
    assert engine.needs_strider("create_calendar_event")


def test_policy_engine_unknown_spoke():
    from policy.engine import PolicyEngine
    engine = PolicyEngine("nonexistent_spoke")
    assert engine.policy is None
    assert not engine.can_act("anything")


def test_policy_engine_assert_can_act_raises():
    from policy.engine import PolicyEngine
    engine = PolicyEngine("finance")
    with pytest.raises(PermissionError):
        engine.assert_can_act("run_phase_c_production")


# ── Cycle (no real tasks in test DB) ─────────────────────────────────────────

def test_cycle_runs_cleanly():
    """Cycle should complete without exceptions and return a well-formed summary."""
    from cycle import run_cycle
    from context_tracker import ContextTracker

    result = run_cycle(context_tracker=ContextTracker(current_pct=0.0))
    assert "started_at" in result
    assert "ended_at" in result
    assert "tasks_processed" in result
    assert "handoff_triggered" in result
    # No unexpected errors (spoke handler stubs are expected to return skipped=True)
    assert result["errors"] == [], f"Unexpected errors: {result['errors']}"
