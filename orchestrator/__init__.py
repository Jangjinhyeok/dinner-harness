"""Cross-vendor Two-CLI orchestrator.

The external, cross-process sibling of the ``autonomous-loop`` skill: it drives
an Architect vendor and a Builder vendor (Codex / Claude, either direction)
through the file bus (HANDOFF.md / RESULT.md / INPUT.md), replacing the human
relay. The human is invoked only at the boundaries that risk-tiered autonomy
keeps: START intent, conditional HIGH-tier sign-off, and END acceptance.

Stdlib only. Design: docs/architecture (cross-vendor orchestrator).
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
