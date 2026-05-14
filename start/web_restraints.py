"""Optional restraint sidecar files written by the DynaLab web server into a job directory.

``Single_Replica.py``, ``Pulling_Simulations.py``, and ``Replica_Exchange.py`` merge these
into ``run_upside.advanced_config`` when the corresponding files exist and are non-empty.
"""

from __future__ import annotations

import os
from pathlib import Path

from typing import Dict

_SIDE_CARS = (
    ("restraint-fixed-wall.dat", "fixed_wall"),
    ("restraint-pair-wall.dat", "pair_wall"),
    ("restraint-fixed-spring.dat", "fixed_spring"),
    ("restraint-nail.dat", "nail"),
)


def extra_restraint_kwargs(pdb_dir: str | os.PathLike[str]) -> Dict[str, str]:
    """Return kwargs for ``run_upside.advanced_config`` for sidecar ``.dat`` files if present."""
    d = Path(os.path.abspath(os.fspath(pdb_dir)))
    out: Dict[str, str] = {}
    for fname, key in _SIDE_CARS:
        p = d / fname
        if p.is_file() and p.stat().st_size > 0:
            out[key] = str(p.resolve())
    return out
