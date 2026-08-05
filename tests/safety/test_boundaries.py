"""Mechanical architecture-boundary scan, mirrored from scripts/safety_check.sh
so CI enforces the rules even where the shell script isn't run."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "tradeos"


def _py_files(*parts: str) -> list[Path]:
    root = SRC.joinpath(*parts) if parts else SRC
    return sorted(root.rglob("*.py"))


def _grep(pattern: str, files: list[Path]) -> list[str]:
    rx = re.compile(pattern)
    hits = []
    for path in files:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if rx.search(line):
                hits.append(f"{path.relative_to(SRC.parent.parent)}:{lineno}: {line.strip()}")
    return hits


def test_validated_order_constructed_only_in_risk_engine() -> None:
    offenders = [
        hit
        for hit in _grep(r"ValidatedOrder\(", _py_files())
        if "/risk/" not in hit and "/domain/" not in hit
    ]
    assert offenders == [], f"ValidatedOrder constructed outside risk engine: {offenders}"


def test_submit_order_called_only_from_execution_layer() -> None:
    offenders = [hit for hit in _grep(r"\.submit_order\(", _py_files()) if "/execution/" not in hit]
    assert offenders == [], f"submit_order called outside execution layer: {offenders}"


def test_interfaces_do_not_import_core_internals() -> None:
    pattern = r"from tradeos\.(brokers|providers|risk|execution|storage)\b"
    offenders = _grep(pattern, _py_files("cli") + _py_files("tui"))
    assert offenders == [], f"interface layer bypasses the facade: {offenders}"


def test_strategies_and_providers_never_touch_brokers() -> None:
    offenders = _grep(r"from tradeos\.brokers\b", _py_files("strategies") + _py_files("providers"))
    assert offenders == []


def test_no_shell_true_or_eval() -> None:
    assert _grep(r"shell=True", _py_files()) == []
    assert _grep(r"(^|[^\w.])eval\(", _py_files()) == []


def test_domain_and_risk_never_read_wall_clock() -> None:
    """Rules/strategies receive time via injection. Direct clock reads are
    confined to domain/common.py (utc_now) and domain/clock.py."""
    files = [
        p
        for p in _py_files("risk") + _py_files("strategies") + _py_files("domain")
        if p.name not in {"common.py", "clock.py"}
    ]
    offenders = _grep(r"datetime\.now\(|time\.time\(|utc_now\(\)", files)
    assert offenders == [], f"uninjected clock reads: {offenders}"
