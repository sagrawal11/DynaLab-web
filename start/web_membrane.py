"""Read membrane settings from DynaLab ``config.json`` for web/CLI simulations.

``find_dynalab_config`` walks upward from ``pdb_dir`` so sweep sub-jobs under
``.../sweeps/<id>/F_*_rep_*`` still resolve the job-level config at ``<job>/config.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_dynalab_config(job_root: str | Path) -> dict[str, Any] | None:
    cur = Path(job_root).resolve()
    for _ in range(10):
        p = cur / "config.json"
        if p.is_file():
            try:
                data = json.loads(p.read_text())
            except Exception:
                return None
            if isinstance(data, dict) and (
                "membraneEnabled" in data
                or "simulationMode" in data
                or "duration" in data
            ):
                return data
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def upside_recentering_flags(cfg: dict[str, Any] | None) -> str:
    """Return trailing ``obj/upside`` CLI flags for recentering.

    When the membrane card is off (or no config), match legacy behavior:
    ``--disable-recentering``. When membrane is enabled, honor the two
    disable-* checkboxes; if both are unchecked, omit recentering-disable flags.
    """
    if cfg is None or not cfg.get("membraneEnabled"):
        return "--disable-recentering "
    parts: list[str] = []
    if cfg.get("membraneDisableRecentering"):
        parts.append("--disable-recentering")
    if cfg.get("membraneDisableZRecentering"):
        parts.append("--disable-z-recentering")
    if not parts:
        return ""
    return " ".join(parts) + " "


def membrane_kwargs_for_upside(
    cfg: dict[str, Any] | None,
    *,
    param_dir_ff: str,
    legacy_pulling_default: bool,
) -> dict[str, Any]:
    """Return ``run_upside.upside_config`` kwargs for implicit membrane (may be empty).

    * **legacy_pulling_default** — if there is no DynaLab config file, behave like
      historical ``Pulling_Simulations.py`` (implicit membrane, thickness 31.8).
    * If config exists and ``membraneEnabled`` is false, return ``{}`` (no membrane).
    * If ``membraneEnabled`` is true, add ``membrane_potential``, ``membrane_thickness``,
      and optional curvature flags when coordinate system is ``spherical``.
    """
    if cfg is None:
        if legacy_pulling_default:
            return {
                "membrane_potential": param_dir_ff + "membrane.h5",
                "membrane_thickness": 31.8,
            }
        return {}
    if not cfg.get("membraneEnabled"):
        return {}
    try:
        inner = float(cfg.get("membraneInnerAngstrom", -16))
        outer = float(cfg.get("membraneOuterAngstrom", 16))
    except (TypeError, ValueError):
        inner, outer = -16.0, 16.0
    if outer <= inner:
        outer = inner + 4.0
    thickness = max(4.0, min(120.0, outer - inner))
    out: dict[str, Any] = {
        "membrane_potential": param_dir_ff + "membrane.h5",
        "membrane_thickness": thickness,
    }
    coord = str(cfg.get("membraneCoordSystem") or "cartesian").strip().lower()
    if coord == "spherical":
        out["use_curvature"] = True
        try:
            out["curvature_radius"] = float(cfg.get("membraneCurvatureRadius", 200.0))
        except (TypeError, ValueError):
            out["curvature_radius"] = 200.0
        try:
            out["curvature_sign"] = int(cfg.get("membraneCurvatureSign", 1))
        except (TypeError, ValueError):
            out["curvature_sign"] = 1
    return out
