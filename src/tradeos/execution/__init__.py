"""Execution layer: the ONLY caller of broker.submit_order (ARCHITECTURE §2)."""

from tradeos.execution.executor import ExecutionHalted, Executor

__all__ = ["ExecutionHalted", "Executor"]
