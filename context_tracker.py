"""
Context window usage tracker.
Elrond uses this to decide when to hand off to a fresh session.

In a CCR session, Claude Code exposes context usage through the TaskGet tool
or environment. For now we use a conservative manual counter — the CCR prompt
can seed this with the actual context percentage at session start.
"""
from __future__ import annotations

import os


class ContextTracker:
    """
    Tracks approximate context window usage for the current Elrond session.

    Usage:
        tracker = ContextTracker(current_pct=0.20)
        tracker.add_tokens(1500)
        if tracker.should_handoff():
            ...
    """

    # Rough token-to-percentage mapping for claude-sonnet-4-6 (200k context)
    _TOKENS_PER_PCT = 2000  # 1% ≈ 2,000 tokens

    def __init__(self, current_pct: float = 0.0, threshold: float | None = None):
        """
        current_pct: context window already used at session start (0.0–1.0)
        threshold: override the handoff threshold (defaults to env var or 0.45)
        """
        self._pct = current_pct
        self._threshold = threshold or float(
            os.environ.get("CONTEXT_HANDOFF_THRESHOLD", "0.45")
        )

    @property
    def current_pct(self) -> float:
        return self._pct

    def set_pct(self, pct: float) -> None:
        """Directly set context usage (e.g. from TaskGet output)."""
        self._pct = max(0.0, min(1.0, pct))

    def add_tokens(self, estimated_tokens: int) -> None:
        """Increment by estimated token count."""
        self._pct += estimated_tokens / (self._TOKENS_PER_PCT * 100)
        self._pct = min(1.0, self._pct)

    def should_handoff(self) -> bool:
        """True if context usage is at or above the handoff threshold."""
        return self._pct >= self._threshold

    def __repr__(self) -> str:
        return (
            f"ContextTracker(current={self._pct:.1%}, "
            f"threshold={self._threshold:.1%}, "
            f"handoff={'YES' if self.should_handoff() else 'no'})"
        )
