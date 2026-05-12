"""
Elrond policy engine.
Wraps elrond_policy lookups with convenience methods.
"""
from __future__ import annotations

from mongo.client import get_collection, ELROND_POLICY


class PolicyEngine:
    """
    Loads and enforces the active policy for a given spoke.

    Usage:
        engine = PolicyEngine("finance")
        if engine.can_act("run_phase_a"):
            ...
        elif engine.needs_strider("request_missing_customer_mapping"):
            ...
    """

    def __init__(self, spoke: str):
        self.spoke = spoke
        self.policy = self._load(spoke)

    @staticmethod
    def _load(spoke: str) -> dict | None:
        coll = get_collection(ELROND_POLICY)
        return coll.find_one({"spoke": spoke, "active": True})

    def can_act(self, action: str) -> bool:
        """True if Elrond can take this action autonomously."""
        if not self.policy:
            return False
        return action in (self.policy.get("autonomous_actions") or [])

    def needs_strider(self, action: str) -> bool:
        """True if this action requires human input via Strider."""
        if not self.policy:
            return False
        return action in (self.policy.get("requires_strider") or [])

    def needs_stephan(self, action: str) -> bool:
        """True if this action requires direct Stephan approval."""
        if not self.policy:
            return False
        return action in (self.policy.get("requires_stephan") or [])

    @property
    def max_retries(self) -> int:
        return (self.policy or {}).get("max_subagent_retries", 3)

    @property
    def max_spend(self) -> float:
        return (self.policy or {}).get("max_spend_per_run", 1.0)

    @property
    def handoff_threshold(self) -> float:
        return (self.policy or {}).get("context_handoff_threshold", 0.45)

    def assert_can_act(self, action: str) -> None:
        """Raise if action is not in autonomous_actions."""
        if not self.can_act(action):
            raise PermissionError(
                f"Policy '{self.spoke}': action '{action}' not in autonomous_actions. "
                f"needs_strider={self.needs_strider(action)}, "
                f"needs_stephan={self.needs_stephan(action)}"
            )
