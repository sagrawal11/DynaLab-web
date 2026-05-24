#!/usr/bin/env python3
"""Make sure the PDBs referenced by ``matrix.json`` exist on disk.

If a case lists a ``pdb_source`` that already exists in the repo (e.g. one of
the files under ``example/``), nothing is downloaded. Otherwise the script
fetches the PDB from RCSB using stdlib ``urllib`` (no extra dependencies) and
writes it to ``benchmarks/proteins/<pdb_id>.pdb``.

You can also pre-populate ``benchmarks/proteins/`` manually if you have a
specific structure file you want to benchmark — just point the matrix at it.

Examples
--------
::

    python benchmarks/scripts/fetch_proteins.py
    python benchmarks/scripts/fetch_proteins.py --matrix benchmarks/matrix.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


RCSB_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"


def _project_root() -> Path:
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from dynalab_paths import find_dynalab_root

    return find_dynalab_root()


def download(pdb_id: str, dest: Path, timeout: float = 30.0) -> bool:
    url = RCSB_URL.format(pdb_id=pdb_id.upper())
    try:
        with urlopen(url, timeout=timeout) as resp:
            data = resp.read()
    except (HTTPError, URLError) as exc:
        print(f"  download failed for {pdb_id}: {exc}", file=sys.stderr)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    here = Path(__file__).resolve()
    repo = _project_root()
    ap.add_argument("--matrix", default=str(repo / "benchmarks" / "matrix.json"))
    ap.add_argument("--proteins-dir", default=str(repo / "benchmarks" / "proteins"))
    return ap.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    matrix_path = Path(args.matrix)
    if not matrix_path.is_file():
        print(f"matrix not found: {matrix_path}", file=sys.stderr)
        return 2
    matrix = json.loads(matrix_path.read_text())
    repo = _project_root()
    proteins_dir = Path(args.proteins_dir)
    proteins_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    for case in matrix:
        src = case.get("pdb_source")
        pid = case.get("pdb_id")
        if not src or not pid:
            continue
        if (pid, src) in seen:
            continue
        seen.add((pid, src))

        src_path = Path(src)
        if not src_path.is_absolute():
            src_path = repo / src_path
        if src_path.is_file():
            print(f"OK    {pid:<10s} {src_path}")
            continue

        # Auto-fetch into proteins_dir
        target = proteins_dir / f"{pid}.pdb"
        if target.is_file():
            print(f"have  {pid:<10s} {target}")
            continue
        print(f"fetch {pid:<10s} -> {target}")
        if not download(pid, target):
            print(f"  WARNING: could not fetch {pid}; the matrix case will fail.",
                  file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
