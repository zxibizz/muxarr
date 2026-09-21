"""The layering rules, enforced.

Dependencies point inward: api -> application -> domain, with infrastructure
implementing the application's contracts. Nothing below api may import FastAPI.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

# domain/models.py is the one carve-out: the ORM mapping has to live with the
# entity it maps, as it does in the sibling projects this layout follows.
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "domain": ("src.api", "src.application", "src.infrastructure", "fastapi", "sqlalchemy"),
    "application": ("src.api", "src.infrastructure", "fastapi", "sqlalchemy"),
    "infrastructure": ("src.api", "fastapi"),
    # The worker is a separate process; dragging the web stack in would mean
    # the two could no longer be deployed apart.
    "worker": ("src.api", "fastapi", "uvicorn"),
}

EXEMPT = {"domain/models.py"}


def _modules(layer: str) -> list[Path]:
    return sorted(p for p in (SRC / layer).rglob("*.py"))


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layer_does_not_import_outwards(layer: str) -> None:
    banned = FORBIDDEN[layer]
    violations: list[str] = []

    for path in _modules(layer):
        relative = path.relative_to(SRC).as_posix()
        if relative in EXEMPT:
            continue
        for name in _imported_names(path):
            if any(name == b or name.startswith(f"{b}.") for b in banned):
                violations.append(f"{relative} imports {name}")

    assert not violations, "layering violation:\n  " + "\n  ".join(violations)


def test_the_exempt_list_stays_honest() -> None:
    """A stale exemption silently reopens the boundary it was carved out of."""
    for relative in EXEMPT:
        assert (SRC / relative).is_file(), f"{relative} no longer exists"
