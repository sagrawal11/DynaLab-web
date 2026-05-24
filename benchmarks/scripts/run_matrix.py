#!/usr/bin/env python3
"""Run a benchmark matrix and produce one ``result.json`` per case.

The matrix file is a JSON list of case objects (see ``benchmarks/matrix.json``).
Each case has at minimum:

    case_id, mode, pdb_id, pdb_source, duration, frame_interval

Filtering:
    --tier <name>   only cases with matching ``tier`` field
    --only <id>     only the case with matching ``case_id``
    --skip <id>     skip the case with matching ``case_id`` (repeatable)

After the matrix runs, this script also writes a ``status.json`` summary at the
output directory root, listing which cases succeeded and which failed.

Examples
--------
::

    python benchmarks/scripts/run_matrix.py \\
        --matrix benchmarks/matrix.json \\
        --output-dir benchmarks/results/aws \\
        --tier aws

    python benchmarks/scripts/run_matrix.py \\
        --matrix benchmarks/matrix.json \\
        --output-dir benchmarks/results/smoke \\
        --only smoke_chig
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_one import _project_root_from, run_case  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", required=True, help="Path to matrix.json")
    ap.add_argument("--output-dir", required=True, help="Where to write per-case result dirs")
    ap.add_argument("--tier", default=None, help="Only run cases with this tier")
    ap.add_argument("--only", default=None, help="Only run this single case_id")
    ap.add_argument("--skip", action="append", default=[], help="case_id to skip (repeatable)")
    ap.add_argument("--continue-on-fail", action="store_true",
                    help="Keep running after a case fails (default: yes; overridden by --stop-on-fail)")
    ap.add_argument("--stop-on-fail", action="store_true",
                    help="Stop the matrix as soon as one case fails")
    return ap.parse_args(argv)


def select_cases(matrix: list[dict], args: argparse.Namespace) -> list[dict]:
    skip = set(args.skip or [])
    out: list[dict] = []
    for c in matrix:
        if args.only and c.get("case_id") != args.only:
            continue
        if args.tier and c.get("tier") != args.tier:
            continue
        if c.get("case_id") in skip:
            continue
        out.append(c)
    return out


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    matrix = json.loads(Path(args.matrix).read_text())
    if not isinstance(matrix, list):
        print("matrix.json must be a JSON list of cases", file=sys.stderr)
        return 2

    cases = select_cases(matrix, args)
    if not cases:
        print("No cases matched the filter.", file=sys.stderr)
        return 2

    upside_home = _project_root_from(os.environ.get("UPSIDE_HOME"))
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Matrix run: {len(cases)} case(s) -> {output_dir}")
    print(f"UPSIDE_HOME={upside_home}")
    print(f"Cases: {[c['case_id'] for c in cases]}")
    print()

    statuses: list[dict] = []
    overall_started = time.time()

    for i, case in enumerate(cases, 1):
        cid = case["case_id"]
        case_started = time.time()
        print(f"[{i}/{len(cases)}] {cid} (mode={case['mode']}, "
              f"protein={case.get('pdb_id', '?')}, duration={case.get('duration', '?')})")
        try:
            result = run_case(case, output_dir, upside_home)
        except Exception as exc:
            elapsed = time.time() - case_started
            print(f"  FAILED ({elapsed:.1f}s): {type(exc).__name__}: {exc}")
            statuses.append({
                "case_id": cid, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                "wall_seconds": elapsed,
            })
            if args.stop_on_fail:
                break
            continue

        result_path = output_dir / cid / "result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=2, default=str))

        elapsed = time.time() - case_started
        ok = bool(result.get("ok"))
        wall = result.get("wall_seconds", elapsed)
        rss_mb = result.get("peak_rss_mb", 0.0)
        out_mb = result.get("output_mb", 0.0)
        status_word = "OK " if ok else "FAIL"
        print(f"  {status_word} wall={wall:.1f}s peak_rss={rss_mb:.0f}MB output={out_mb:.1f}MB")
        statuses.append({
            "case_id": cid, "ok": ok, "wall_seconds": wall,
            "peak_rss_mb": rss_mb, "output_mb": out_mb,
            "exit_code": result.get("exit_code"),
        })
        if not ok and args.stop_on_fail:
            break

    overall_elapsed = time.time() - overall_started
    summary = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(overall_started)),
        "elapsed_seconds": overall_elapsed,
        "case_count": len(cases),
        "ok_count": sum(1 for s in statuses if s["ok"]),
        "fail_count": sum(1 for s in statuses if not s["ok"]),
        "cases": statuses,
    }
    (output_dir / "status.json").write_text(json.dumps(summary, indent=2, default=str))

    print()
    print(f"Matrix done: {summary['ok_count']}/{summary['case_count']} OK "
          f"in {overall_elapsed/60:.1f} min")
    print(f"Wrote {output_dir / 'status.json'}")

    return 0 if summary["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
