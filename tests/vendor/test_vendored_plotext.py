"""The vendored copy must import and render from its new location.

Vendoring required editing imports, so these guard the edits rather than
plotext itself. A failure here means the vendored tree was updated without
reapplying the changes documented in src/tradeos/vendor/README.md.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

VENDOR = pathlib.Path(__file__).resolve().parents[2] / "src" / "tradeos" / "vendor" / "plotext"


def test_imports_and_renders() -> None:
    from tradeos.vendor import plotext as plt

    plt.clear_figure()
    plt.theme("clear")
    plt.plotsize(40, 10)
    plt.plot([1, 2, 3, 4], [1, 4, 2, 5], marker="hd")
    out = plt.build()
    assert out.strip(), "vendored plotext produced an empty canvas"


def test_no_absolute_self_imports() -> None:
    """`from plotext...` only resolves at the top level, which this is not."""
    offenders = []
    for path in sorted(VENDOR.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [
                    f"{path.name}:{node.lineno}"
                    for a in node.names
                    if a.name.split(".")[0] == "plotext"
                ]
            elif (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
                and node.module.split(".")[0] == "plotext"
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"absolute self-imports would break vendoring: {offenders}"


def test_name_is_not_reassigned() -> None:
    """Reassigning ``__name__`` breaks every relative import in the package.

    Checked against the parse tree, not the text, so the comment in
    ``__init__.py`` explaining the removal does not trip it.
    """
    tree = ast.parse((VENDOR / "__init__.py").read_text())
    assigned = [
        t.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name)
    ]
    assert "__name__" not in assigned


def test_licence_is_present() -> None:
    licence = VENDOR / "LICENSE"
    assert licence.is_file(), "vendored code must keep its licence"
    assert "MIT" in licence.read_text()


@pytest.mark.parametrize("marker", ["hd", "fhd", "braille"])
def test_markers_render(marker: str) -> None:
    from tradeos.vendor import plotext as plt

    plt.clear_figure()
    plt.theme("clear")
    plt.plotsize(30, 8)
    plt.plot([1, 2, 3, 4, 5], [2, 4, 3, 6, 5], marker=marker)
    assert plt.build().strip()
