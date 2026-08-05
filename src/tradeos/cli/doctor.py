"""Backwards-compatible re-export.

The checks moved to ``tradeos.runtime.diagnostics`` so the TUI boot sequence can
reach them through the facade without importing CLI code (ARCHITECTURE §2).
"""

from __future__ import annotations

from tradeos.runtime.diagnostics import CheckStatus, DoctorCheck, run_checks

__all__ = ["CheckStatus", "DoctorCheck", "run_checks"]
