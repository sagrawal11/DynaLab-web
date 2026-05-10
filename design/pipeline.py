"""Orchestrate the AI nanobody design pipeline.

Given a Phase 1 epitope candidate + a Phase 2 back-mapped intermediate
all-atom PDB, run RFdiffusion -> ProteinMPNN -> AlphaFold-Multimer end-to-end
and write the ranked candidates to the job's ``design/<design_id>/`` dir.

The orchestrator picks between :class:`TamarindClient` (real) and
:class:`MockTamarindClient` (deterministic stub) based on whether
``TAMARIND_API_KEY`` is configured. The web UI flips a switch in
``Settings`` to set/clear that key, so a developer running offline gets
the mock without any code changes.

Output layout::

    jobs/<job_id>/design/<design_id>/
        request.json          # what the caller asked for
        manifest.json         # current status / final ranking
        candidates/
            rank_001.pdb      # top binder structures (real client only)
            rank_002.pdb
            ...
        scores.json           # ipTM/pTM/pLDDT for every candidate

`run_design_pipeline()` is the only public entry point and is what
``web/server/app.py`` invokes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterable


def _make_client(prefer_mock: bool = False):
    """Return either a real Tamarind client or the deterministic mock.

    Falls back to the mock automatically when ``TAMARIND_API_KEY`` is unset
    or ``requests`` isn't installed.
    """
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    if prefer_mock:
        from tamarind_mock import MockTamarindClient
        return MockTamarindClient(), "mock"

    try:
        from tamarind_client import TamarindClient, TamarindError
        return TamarindClient(), "real"
    except Exception as exc:                  # ImportError, missing key, etc.
        from tamarind_mock import MockTamarindClient
        client = MockTamarindClient()
        client._fallback_reason = f"{type(exc).__name__}: {exc}"   # type: ignore[attr-defined]
        return client, "mock-fallback"


def _read_pdb_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Intermediate PDB not found: {path}")
    return path.read_text()


def _resolve_intermediate(
    job_dir: Path,
    intermediate_state: str,
) -> Path:
    """Locate the all-atom (back-mapped) PDB that matches ``intermediate_state``.

    ``intermediate_state`` can be ``intermediate_03`` (matching one of the
    files in ``backmapped/``) or just ``03`` / ``3``.
    """
    bm_dir = job_dir / "backmapped"
    if not bm_dir.exists():
        raise FileNotFoundError(
            f"No backmapped/ directory in {job_dir}. Run back-mapping first."
        )

    candidate = bm_dir / f"{intermediate_state}.pdb"
    if candidate.is_file():
        return candidate
    candidate = bm_dir / f"{intermediate_state}_aa.pdb"
    if candidate.is_file():
        return candidate

    if intermediate_state.isdigit():
        idx = int(intermediate_state)
        for variant in (
            f"intermediate_{idx:02d}_aa.pdb",
            f"intermediate_{idx:02d}.rebuilt.pdb",
            f"intermediate_{idx:02d}.pdb",
        ):
            candidate = bm_dir / variant
            if candidate.is_file():
                return candidate

    available = sorted(p.name for p in bm_dir.glob("*.pdb"))
    raise FileNotFoundError(
        f"Could not match intermediate '{intermediate_state}' in {bm_dir}. "
        f"Available: {available}"
    )


def _save_candidates(
    design_dir: Path,
    af_result: dict,
    mpnn_result: dict,
    rf_result: dict,
) -> list:
    """Write top candidates as rank_001.pdb, rank_002.pdb, ...

    For the mock client the "PDB content" is a placeholder string so we just
    write the metadata as a JSON sidecar -- enough for the UI to render a
    candidate list. For the real client the binder PDBs come back from
    Tamarind as ``pdb`` fields on each AF score row.
    """
    candidates_dir = design_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for rank, score in enumerate(af_result.get("scores", []), start=1):
        meta = {
            "rank":            rank,
            "iptm":            score.get("iptm"),
            "ptm":             score.get("ptm"),
            "plddt_mean":      score.get("plddt_mean"),
            "binder_sequence": score.get("binder_sequence"),
            "binder_index":    score.get("binder_index"),
        }
        pdb_text = score.get("pdb")
        out = candidates_dir / f"rank_{rank:03d}.pdb"
        if pdb_text:
            out.write_text(pdb_text)
            meta["pdb_file"] = out.name
        else:
            # Mock path: write a placeholder so the file exists and the UI
            # can still link to it - the manifest carries the real metadata.
            out.write_text(
                "REMARK  Placeholder PDB for mock binder.\n"
                f"REMARK  rank={rank} iptm={score.get('iptm')}\n"
                f"REMARK  sequence={score.get('binder_sequence', '')}\n"
            )
            meta["pdb_file"] = out.name
            meta["placeholder"] = True
        saved.append(meta)
    return saved


def run_design_pipeline(
    job_dir: Path,
    design_dir: Path,
    request_body: dict,
) -> dict:
    """Execute the full RFdiff -> MPNN -> AF-Multimer pipeline.

    ``request_body`` shape::

        {
          "intermediate_state":  "intermediate_03",  # which back-mapped PDB
          "hotspots":            [42, 43, 44],       # epitope residues
          "n_designs":           50,
          "binder_length":       100,
          "n_seqs_per_design":   8,
          "use_mock":            False,              # force the offline mock
        }

    Returns a dict suitable for ``manifest['results']``.
    """
    intermediate_state = request_body.get("intermediate_state")
    if not intermediate_state:
        raise ValueError("request must include 'intermediate_state'")
    hotspots = list(request_body.get("hotspots") or [])
    n_designs = int(request_body.get("n_designs", 50))
    binder_length = int(request_body.get("binder_length", 100))
    n_seqs = int(request_body.get("n_seqs_per_design", 8))
    use_mock = bool(request_body.get("use_mock", False))

    pdb_path = _resolve_intermediate(Path(job_dir), str(intermediate_state))
    pdb_text = _read_pdb_text(pdb_path)

    client, client_kind = _make_client(prefer_mock=use_mock)

    # 1. RFdiffusion
    rf_result = client.run_rfdiffusion(
        target_pdb=pdb_text,
        hotspots=hotspots,
        n_designs=n_designs,
        binder_length=binder_length,
    )
    # 2. ProteinMPNN over each backbone
    mpnn_result = client.run_protein_mpnn(
        pdb_paths=rf_result.get("pdb_paths", []),
        n_seqs=n_seqs,
    )
    binder_sequences = [s["sequence"] for s in mpnn_result.get("sequences", [])]
    # 3. AlphaFold-Multimer ipTM scoring
    target_seq = request_body.get("target_sequence", "")
    if not target_seq:
        # Pull the FASTA from the PDB for convenience.
        try:
            from py.run_upside import chain_endpts  # noqa: F401
        except Exception:
            pass
        # Reading sequence directly from the PDB is sufficient for the API.
        # We just take the one-letter sequence from CA records.
        target_seq = _seq_from_pdb(pdb_path)
    af_result = client.run_af_multimer(
        target_sequence=target_seq,
        binder_sequences=binder_sequences,
        target_pdb=pdb_text,
    )

    candidates = _save_candidates(Path(design_dir), af_result, mpnn_result, rf_result)
    (Path(design_dir) / "scores.json").write_text(json.dumps(af_result, indent=2))
    (Path(design_dir) / "rf_result.json").write_text(json.dumps(rf_result, indent=2))
    (Path(design_dir) / "mpnn_result.json").write_text(json.dumps(mpnn_result, indent=2))

    return {
        "client_kind": client_kind,
        "n_designs":   n_designs,
        "n_sequences": len(binder_sequences),
        "n_scored":    len(af_result.get("scores", [])),
        "candidates":  candidates,
        "intermediate_pdb": str(pdb_path.relative_to(job_dir)),
        "fallback_reason":  getattr(client, "_fallback_reason", None),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


def _seq_from_pdb(pdb_path: Path) -> str:
    seq_chars = []
    seen = set()
    for line in pdb_path.read_text().splitlines():
        if not line.startswith("ATOM"):
            continue
        if line[12:16].strip() != "CA":
            continue
        resname = line[17:20].strip()
        chain = line[21]
        try:
            resseq = int(line[22:26])
        except ValueError:
            continue
        key = (chain, resseq)
        if key in seen:
            continue
        seen.add(key)
        seq_chars.append(_THREE_TO_ONE.get(resname, "X"))
    return "".join(seq_chars)
