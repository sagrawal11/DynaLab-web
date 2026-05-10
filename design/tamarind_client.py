"""Thin REST client for Tamarind Bio's hosted AI protein-design endpoints.

Tamarind Bio exposes three relevant tools as managed APIs:

  - **RFdiffusion**            generate de novo binder backbones around an
                                exposed epitope (CG -> backbone).
  - **ProteinMPNN**            sequence-design those backbones (backbone -> seq).
  - **AlphaFold-Multimer**     score (target+binder) interface confidence
                                via ipTM (sequence -> confidence).

The actual endpoint contract is documented at https://docs.tamarind.bio/.
This client is intentionally minimal: a client object that holds the API
key + endpoint, methods that submit a job and poll until completion, and
no app-level logic. Pipeline orchestration lives in ``design/pipeline.py``.

If the API is unreachable or no key is configured, callers should fall
back to ``tamarind_mock.MockTamarindClient`` -- it implements the same
surface area but returns deterministic synthetic data, which is what we
use in tests and demo runs.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterable

try:
    import requests          # listed in requirements.txt
except ImportError:          # pragma: no cover  - exercised in offline tests
    requests = None          # type: ignore[assignment]


DEFAULT_ENDPOINT = "https://api.tamarind.bio"
DEFAULT_TIMEOUT = 60          # seconds, per request
DEFAULT_POLL_INTERVAL = 5     # seconds, between status polls
DEFAULT_POLL_DEADLINE = 60 * 30  # 30 min total


class TamarindError(RuntimeError):
    """Raised on any Tamarind API failure."""


class TamarindClient:
    """Tamarind REST client.

    Usage::

        client = TamarindClient(api_key=os.environ["TAMARIND_API_KEY"])
        rf_job = client.run_rfdiffusion(target_pdb_str, hotspots=[123, 124])
        designs = client.run_protein_mpnn(rf_job["pdb_paths"], n_seqs=8)
        scores = client.run_af_multimer(target_seq, designs["sequences"])
    """

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        session: object | None = None,
    ):
        self.api_key = api_key or os.environ.get("TAMARIND_API_KEY", "")
        self.endpoint = (
            endpoint
            or os.environ.get("TAMARIND_API_URL", DEFAULT_ENDPOINT)
        ).rstrip("/")
        if not self.api_key:
            raise TamarindError(
                "TAMARIND_API_KEY is not set. "
                "Configure it in web/server/.env or via Settings -> API Key in the UI."
            )
        if requests is None:
            raise TamarindError(
                "The 'requests' package is required for Tamarind. "
                "Install it via web/server/requirements.txt or "
                "the conda environment."
            )
        self._session = session or requests.Session()
        self._session.headers.update({                  # type: ignore[union-attr]
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        })

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _post(self, path: str, json_body: dict) -> dict:
        url = f"{self.endpoint}{path}"
        try:
            r = self._session.post(            # type: ignore[union-attr]
                url, json=json_body, timeout=DEFAULT_TIMEOUT,
            )
        except Exception as exc:
            raise TamarindError(f"POST {url} failed: {type(exc).__name__}: {exc}") from exc
        if r.status_code >= 400:
            raise TamarindError(f"POST {url} -> {r.status_code} {r.text[:200]}")
        return r.json()

    def _get(self, path: str) -> dict:
        url = f"{self.endpoint}{path}"
        try:
            r = self._session.get(             # type: ignore[union-attr]
                url, timeout=DEFAULT_TIMEOUT,
            )
        except Exception as exc:
            raise TamarindError(f"GET {url} failed: {type(exc).__name__}: {exc}") from exc
        if r.status_code >= 400:
            raise TamarindError(f"GET {url} -> {r.status_code} {r.text[:200]}")
        return r.json()

    def _wait_for(self, job_id: str,
                  poll_interval: int = DEFAULT_POLL_INTERVAL,
                  deadline: int = DEFAULT_POLL_DEADLINE) -> dict:
        """Poll ``/jobs/<id>`` until the job finishes or hits the deadline."""
        elapsed = 0
        while elapsed < deadline:
            data = self._get(f"/jobs/{job_id}")
            status = data.get("status")
            if status in ("completed", "failed", "error"):
                return data
            time.sleep(poll_interval)
            elapsed += poll_interval
        raise TamarindError(
            f"Tamarind job {job_id} did not finish within {deadline}s"
        )

    # ------------------------------------------------------------------
    # High-level tools
    # ------------------------------------------------------------------

    def run_rfdiffusion(
        self,
        target_pdb: str,
        hotspots: Iterable[int],
        n_designs: int = 50,
        binder_length: int = 100,
    ) -> dict:
        """Submit an RFdiffusion run and wait for results.

        ``target_pdb`` is the all-atom back-mapped intermediate (PDB content
        as a string, NOT a path). ``hotspots`` is the list of residue indices
        to focus the binder around. Returns
        ``{"job_id": ..., "pdb_paths": [...], "metadata": {...}}``.
        """
        body = {
            "tool":          "rfdiffusion",
            "target_pdb":    target_pdb,
            "hotspots":      list(hotspots),
            "n_designs":     n_designs,
            "binder_length": binder_length,
        }
        data = self._post("/jobs", body)
        return self._wait_for(data["job_id"])

    def run_protein_mpnn(self, pdb_paths: list, n_seqs: int = 8) -> dict:
        """Sequence-design each RFdiffusion backbone with ProteinMPNN."""
        body = {
            "tool":      "protein_mpnn",
            "pdb_paths": list(pdb_paths),
            "n_seqs":    n_seqs,
        }
        data = self._post("/jobs", body)
        return self._wait_for(data["job_id"])

    def run_af_multimer(
        self,
        target_sequence: str,
        binder_sequences: list,
        target_pdb: str | None = None,
    ) -> dict:
        """Score each (target, binder) pair with AlphaFold-Multimer (ipTM)."""
        body = {
            "tool":             "alphafold_multimer",
            "target_sequence":  target_sequence,
            "binder_sequences": list(binder_sequences),
        }
        if target_pdb is not None:
            body["target_pdb"] = target_pdb
        data = self._post("/jobs", body)
        return self._wait_for(data["job_id"])
