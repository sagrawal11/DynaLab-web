"""Centrifuge experiment design sheet generator.

The centrifuge platform plans on tethering protein constructs at multiple
radial positions inside a single tube. Each radial position experiences a
different centrifugal force ``F = m * omega^2 * r``, so a single spin
exposes the same construct to a *gradient* of pulling forces simultaneously.
That gives ~10 parallel data points per spin instead of ~1 with optical
tweezers.

This module:
  1. Computes the centripetal force ``F`` (in pN) at each well/zone for a
     given rotor RPM, radius, and bead mass.
  2. Picks the radii (or rotor speed) that span a chosen target force
     range, e.g. 14-38 pN.
  3. Optionally aligns the zones to *predicted* exposure thresholds from
     the Upside force sweep (Phase 1) so the experiment lands near the
     interesting biology rather than on arbitrary forces.
  4. Emits a markdown design sheet with rotor, well layout, attachment
     chemistry, controls, and analysis plan -- the spec the wet-lab
     student takes to the bench.

Usage::

    from analysis.centrifuge_design import design_centrifuge_experiment
    plan = design_centrifuge_experiment(
        target_pdb="input.pdb",
        predicted_thresholds_pn=[18.5, 26.4],
        n_zones=10,
        target_force_range=(14.0, 38.0),
        attachment="his-tag",
    )
    print(plan["markdown"])

The :func:`compute_zone_forces` and :func:`pick_zone_radii` helpers are
the small numerical primitives; the real value is in the markdown
generator that mixes them with experimental boilerplate.
"""

from __future__ import annotations

import math
from pathlib import Path


# Physical constants
PI = math.pi


# Default centrifuge & bead parameters (Eppendorf-style benchtop micro-centrifuge).
# These can be overridden per call but the defaults match the prototype the
# user has been planning around in the research vision.
DEFAULT_RPM = 14000
DEFAULT_INNER_RADIUS_M = 0.030    # 30 mm from rotor axis to first well
DEFAULT_OUTER_RADIUS_M = 0.085    # 85 mm to bottom of tube
# Streptavidin-coated 1 micron polystyrene bead, mass:
# rho_polystyrene = 1.05 g/cm3 = 1050 kg/m3, V = 4/3 pi r^3 with r=0.5e-6 m
DEFAULT_BEAD_MASS_KG = (4.0 / 3.0) * PI * (0.5e-6) ** 3 * 1050.0


def compute_zone_forces(
    radii_m: list,
    rpm: float = DEFAULT_RPM,
    bead_mass_kg: float = DEFAULT_BEAD_MASS_KG,
) -> list:
    """Return centripetal force in piconewtons at each radius.

    ``F = m * omega^2 * r``. Convert N -> pN by multiplying by 1e12.
    """
    omega = 2.0 * PI * rpm / 60.0  # rad/s
    return [bead_mass_kg * omega ** 2 * r * 1e12 for r in radii_m]


def pick_zone_radii(
    n_zones: int,
    target_force_range: tuple,
    rpm: float = DEFAULT_RPM,
    bead_mass_kg: float = DEFAULT_BEAD_MASS_KG,
) -> list:
    """Choose ``n_zones`` radii that span ``target_force_range`` (pN, inclusive).

    Zones are linearly spaced in *force*, since the user reasons in pN.
    """
    f_min, f_max = float(target_force_range[0]), float(target_force_range[1])
    if f_min <= 0 or f_max <= f_min:
        raise ValueError(f"Bad target_force_range {target_force_range}")

    omega = 2.0 * PI * rpm / 60.0
    radii = []
    for i in range(n_zones):
        if n_zones == 1:
            f = f_min
        else:
            f = f_min + (f_max - f_min) * i / (n_zones - 1)
        # solve F = m omega^2 r for r (m); convert pN back to N first
        r = (f * 1e-12) / (bead_mass_kg * omega ** 2)
        radii.append(r)
    return radii


def _seq_from_pdb(pdb_path: Path) -> str:
    """Extract one-letter sequence from CA records (small helper)."""
    AA3 = {
        "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
        "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
        "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
        "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    }
    seen = set()
    chars = []
    for line in pdb_path.read_text().splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            try:
                rs = (line[21], int(line[22:26]))
            except ValueError:
                continue
            if rs in seen:
                continue
            seen.add(rs)
            chars.append(AA3.get(line[17:20].strip(), "X"))
    return "".join(chars)


def _attachment_protocol(attachment: str) -> str:
    """Return the markdown 'Attachment chemistry' section for the chosen tag."""
    if attachment == "his-tag":
        return (
            "**Attachment chemistry: His-tag / Ni-NTA**\n\n"
            "* Construct: target protein with C-terminal **6xHis tag** + N-terminal\n"
            "  cysteine (or AviTag) for bead attachment.\n"
            "* Surface: glass coverslip functionalized with **Ni-NTA-PEG**.\n"
            "* Bead: streptavidin-coated 1 um polystyrene bead, biotin-PEG-maleimide\n"
            "  cross-linker to the N-terminal cysteine.\n"
            "* Buffer: 50 mM Tris pH 7.5, 150 mM NaCl, 0.05% Tween-20."
        )
    if attachment == "biotin-streptavidin":
        return (
            "**Attachment chemistry: Biotin / Streptavidin**\n\n"
            "* Construct: AviTag-target-AviTag (in-vivo BirA biotinylation).\n"
            "* Surface: streptavidin-functionalized glass.\n"
            "* Bead: streptavidin-coated 1 um polystyrene bead with biotin linker.\n"
            "* Buffer: PBS pH 7.4, 0.05% Tween-20."
        )
    if attachment == "click":
        return (
            "**Attachment chemistry: Click chemistry (SpyTag/SpyCatcher)**\n\n"
            "* Construct: SpyTag-target-SpyTag.\n"
            "* Surface: SpyCatcher-coated glass (covalent bond on contact).\n"
            "* Bead: SpyCatcher-functionalized polystyrene bead."
        )
    return f"_Custom attachment: `{attachment}` (fill in protocol details)._"


def design_centrifuge_experiment(
    target_pdb: str,
    predicted_thresholds_pn: list,
    n_zones: int = 10,
    target_force_range: tuple = (14.0, 38.0),
    rpm: float = DEFAULT_RPM,
    bead_mass_kg: float = DEFAULT_BEAD_MASS_KG,
    attachment: str = "his-tag",
) -> dict:
    """Produce a complete centrifuge experiment design.

    Returns ``{"radii_m": [...], "forces_pn": [...], "rpm": ..., "markdown": ...}``.
    """
    radii_m = pick_zone_radii(n_zones, target_force_range, rpm, bead_mass_kg)
    forces_pn = compute_zone_forces(radii_m, rpm, bead_mass_kg)

    sequence = ""
    pdb_path = Path(target_pdb)
    if pdb_path.is_file():
        sequence = _seq_from_pdb(pdb_path)

    # Build the markdown sheet
    lines = []
    lines.append("# Centrifuge Force-Sweep Experiment Sheet\n")
    lines.append(
        f"**Target protein:** `{pdb_path.name}` "
        f"({len(sequence)} residues)" if sequence else
        f"**Target protein:** `{pdb_path.name}`"
    )
    lines.append("")
    lines.append("## Goal\n")
    lines.append(
        "Validate Upside-predicted cryptic-epitope binders by exposing the "
        "target protein to a controlled gradient of pulling forces in a single "
        "tube and reading out fluorescence-tagged binder occupancy at each force."
    )
    lines.append("")
    lines.append("## Force gradient\n")
    lines.append(f"* Rotor speed: **{rpm:.0f} RPM**")
    lines.append(f"* Bead mass: {bead_mass_kg * 1e15:.2f} fg (default 1 um polystyrene bead)")
    lines.append(f"* Target force range: {target_force_range[0]:.1f} - {target_force_range[1]:.1f} pN")
    lines.append(f"* Number of radial zones: {n_zones}")
    lines.append("")
    lines.append("| Zone | Radius (mm) | Predicted force (pN) | Notes |")
    lines.append("|------|-------------|----------------------|-------|")
    for i, (r, f) in enumerate(zip(radii_m, forces_pn), start=1):
        note = "expected force"
        for thr in (predicted_thresholds_pn or []):
            if abs(f - thr) <= 1.0:
                note = f"~ Upside threshold {thr:.1f} pN"
                break
        lines.append(f"| {i} | {r * 1000:.2f} | {f:.1f} | {note} |")
    lines.append("")
    if predicted_thresholds_pn:
        lines.append("## Predicted exposure thresholds (from Upside)\n")
        for thr in predicted_thresholds_pn:
            lines.append(f"* {thr:.1f} pN")
        lines.append("")
    lines.append("## Constructs\n")
    if sequence:
        lines.append("Target protein sequence:")
        lines.append("```")
        for i in range(0, len(sequence), 60):
            lines.append(sequence[i: i + 60])
        lines.append("```")
        lines.append("")
    lines.append(_attachment_protocol(attachment))
    lines.append("")
    lines.append("## Controls\n")
    lines.append(
        "* **No-spin control** (zone 0, no centrifugation) - pure binding signal at zero force.\n"
        "* **Scrambled-CDR binder** - same chemistry, randomised CDR loops; no force-specific binding expected.\n"
        "* **Disulfide-stapled target** - target with engineered disulfides locking the cryptic epitope shut.\n"
        "* **Positive force control** (e.g. fluorescent tension sensor) confirms the force gradient is intact."
    )
    lines.append("")
    lines.append("## Read-out\n")
    lines.append(
        "* Confocal scan of each zone, integrate fluorescence per construct.\n"
        "* Plot fluorescence vs zone-force; expect sigmoidal activation near a "
        "predicted threshold for the primary binder, flat baselines for the "
        "negative controls."
    )
    lines.append("")
    lines.append("## Spin protocol\n")
    lines.append(
        "1. Pre-block surfaces with BSA 1 mg/mL for 30 min.\n"
        "2. Tether constructs to surface, anneal beads via specific chemistry.\n"
        "3. Add fluorescent binder (5x Kd) and equilibrate 10 min.\n"
        "4. Spin at the chosen RPM for **5 min**.\n"
        "5. Stop without disturbing tube; image immediately on confocal.\n"
        "6. Repeat at zero RPM for the no-spin control."
    )
    lines.append("")
    lines.append("## Linkage to Upside computation\n")
    lines.append(
        "* The **predicted force** column above is what Upside computed. "
        "The wet-lab readout column gets filled in after the spin and uploaded\n"
        "  via `POST /api/jobs/<id>/experimental` (a CSV with columns `force_pN, "
        "fluorescence, replicate, condition`).\n"
        "* `analysis/dynalab_analysis.analyze_force_binding_comparison` will "
        "then overlay the wet-lab points on the Upside prediction in the "
        "Compare-with-experiment tab."
    )
    lines.append("")

    markdown = "\n".join(lines)

    return {
        "rpm":                     rpm,
        "bead_mass_kg":            bead_mass_kg,
        "n_zones":                 n_zones,
        "target_force_range":      list(target_force_range),
        "radii_m":                 radii_m,
        "forces_pn":               forces_pn,
        "predicted_thresholds_pn": list(predicted_thresholds_pn or []),
        "attachment":              attachment,
        "markdown":                markdown,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("target_pdb")
    p.add_argument("--n-zones", type=int, default=10)
    p.add_argument("--rpm", type=float, default=DEFAULT_RPM)
    p.add_argument("--force-low",  type=float, default=14.0)
    p.add_argument("--force-high", type=float, default=38.0)
    p.add_argument("--predicted-thresholds", default="",
                   help="Comma-separated predicted thresholds in pN.")
    p.add_argument("--attachment",
                   choices=("his-tag", "biotin-streptavidin", "click"),
                   default="his-tag")
    p.add_argument("--output", default="experiment_design.md")
    args = p.parse_args()

    thresh = [float(x) for x in args.predicted_thresholds.split(",")
              if x.strip()] if args.predicted_thresholds else []
    plan = design_centrifuge_experiment(
        target_pdb=args.target_pdb,
        predicted_thresholds_pn=thresh,
        n_zones=args.n_zones,
        target_force_range=(args.force_low, args.force_high),
        rpm=args.rpm,
        attachment=args.attachment,
    )
    Path(args.output).write_text(plan["markdown"])
    print(json.dumps({k: v for k, v in plan.items() if k != "markdown"}, indent=2))
    print(f"\nDesign sheet written to: {args.output}")
