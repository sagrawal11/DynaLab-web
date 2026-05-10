"""Deterministic mock of TamarindClient for tests + offline runs.

Implements the same three high-level methods (``run_rfdiffusion``,
``run_protein_mpnn``, ``run_af_multimer``) but returns synthetic data so
the rest of the design pipeline (``design/pipeline.py``) can be exercised
without an API key.

Useful for:
  * CI tests of the orchestrator + Flask endpoints.
  * Demo videos of the UI when offline.
  * Quick local development before signing up for Tamarind Bio.

The mock generates n_designs random short sequences over the canonical
amino-acid alphabet (excluding cysteine) and assigns each candidate an
ipTM score sampled from Beta(2, 2) so that the distribution is reasonable
but not always good. The top three sequences get a small score boost so
the demo always has a clear winner.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Iterable

# Avoid cysteine - real binder design pipelines exclude it to dodge
# spurious disulfide formation.
_AA = "ACDEFGHIKLMNPQRSTVWY".replace("C", "")


def _seeded_rng(seed_str: str) -> random.Random:
    """Deterministic RNG seeded from ``seed_str`` (any input string)."""
    h = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


class MockTamarindClient:
    """No-network client used by tests, demos, and unconfigured environments."""

    def __init__(self, api_key: str = "mock", endpoint: str = "mock://"):
        self.api_key = api_key
        self.endpoint = endpoint

    # ------------------------------------------------------------------
    # RFdiffusion
    # ------------------------------------------------------------------

    def run_rfdiffusion(
        self,
        target_pdb: str,
        hotspots: Iterable[int],
        n_designs: int = 50,
        binder_length: int = 100,
    ) -> dict:
        rng = _seeded_rng(f"rfdiff:{target_pdb[:200]}:{list(hotspots)}:{n_designs}")
        # Each design gets a fake PDB string. We don't try to make these
        # parseable - they're placeholders the test suite can compare to
        # confirm the data flowed through the pipeline.
        designs = []
        for i in range(n_designs):
            designs.append({
                "design_id": f"rf_{i:03d}",
                "pdb_path":  f"mock://design/rf_{i:03d}.pdb",
                "binder_length": binder_length,
                "rmsd_to_motif_A": rng.uniform(0.5, 2.5),
            })
        return {
            "job_id":   f"mock-rfdiff-{rng.randrange(1 << 32):08x}",
            "status":   "completed",
            "pdb_paths": [d["pdb_path"] for d in designs],
            "designs":  designs,
            "metadata": {"tool": "rfdiffusion", "n_designs": n_designs},
        }

    # ------------------------------------------------------------------
    # ProteinMPNN
    # ------------------------------------------------------------------

    def run_protein_mpnn(self, pdb_paths: list, n_seqs: int = 8) -> dict:
        sequences = []
        for pp in pdb_paths:
            rng = _seeded_rng(f"mpnn:{pp}")
            for s_idx in range(n_seqs):
                length = rng.randint(80, 120)
                seq = "".join(rng.choice(_AA) for _ in range(length))
                sequences.append({
                    "design_id": Path(pp).stem,
                    "seq_id":    f"{Path(pp).stem}_seq{s_idx}",
                    "sequence":  seq,
                    "score":     -rng.uniform(0.5, 2.5),
                })
        return {
            "job_id":    f"mock-mpnn-{abs(hash(tuple(pdb_paths))) % (1 << 32):08x}",
            "status":    "completed",
            "sequences": sequences,
            "metadata":  {"tool": "protein_mpnn", "n_seqs": n_seqs},
        }

    # ------------------------------------------------------------------
    # AlphaFold-Multimer
    # ------------------------------------------------------------------

    def run_af_multimer(
        self,
        target_sequence: str,
        binder_sequences: list,
        target_pdb: str | None = None,
    ) -> dict:
        scored = []
        for i, seq in enumerate(binder_sequences):
            rng = _seeded_rng(f"af:{target_sequence[:50]}:{seq}")
            iptm = rng.betavariate(2, 2) * 0.6 + 0.2
            if i < 3:
                iptm = min(0.95, iptm + 0.2)  # ensure some clear top hits
            scored.append({
                "binder_index":  i,
                "binder_sequence": seq,
                "iptm":          round(iptm, 3),
                "ptm":           round(min(0.99, iptm + 0.05), 3),
                "plddt_mean":    round(rng.uniform(60, 90), 1),
            })
        scored.sort(key=lambda d: d["iptm"], reverse=True)
        return {
            "job_id":    f"mock-af-{abs(hash(target_sequence + str(len(binder_sequences)))) % (1 << 32):08x}",
            "status":    "completed",
            "scores":    scored,
            "metadata":  {"tool": "alphafold_multimer", "n_binders": len(binder_sequences)},
        }
