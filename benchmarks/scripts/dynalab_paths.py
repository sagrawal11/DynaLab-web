"""Resolve the DynaLab repo root (``UPSIDE_HOME``) reliably.

The dev container image sets ``UPSIDE_HOME=/upside2-md`` (the baked-in clone),
but day-to-day development bind-mounts the real checkout under ``/workspaces/…``.
Benchmark scripts must use the mounted tree, not the stale image path.
"""

from __future__ import annotations

import os
from pathlib import Path

_MARKER = (
    ("start", "Single_Replica.py"),
    ("benchmarks", "matrix.json"),
)


def is_dynalab_root(path: Path) -> bool:
    return all((path / a / b).is_file() for a, b in _MARKER)


def find_dynalab_root() -> Path:
    """Return the DynaLab repo root, preferring a valid tree over a stale env var."""
    env = os.environ.get("UPSIDE_HOME", "").strip()

    if env:
        candidate = Path(env)
        if is_dynalab_root(candidate):
            return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        if is_dynalab_root(parent):
            return parent

    workspaces = Path("/workspaces")
    if workspaces.is_dir():
        for child in sorted(workspaces.iterdir()):
            if child.is_dir() and is_dynalab_root(child):
                return child

    fallback = Path("/upside2-md")
    if is_dynalab_root(fallback):
        return fallback

    if env:
        raise RuntimeError(
            f"UPSIDE_HOME={env!r} is set but is not a DynaLab checkout "
            f"(missing start/Single_Replica.py). Unset it or point it at your "
            f"mounted repo, e.g. export UPSIDE_HOME=/workspaces/DynaLab-merge-dynalab"
        )
    raise RuntimeError(
        "Cannot locate DynaLab repo root. Run from inside the repo or set UPSIDE_HOME."
    )
