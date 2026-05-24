#!/usr/bin/env python3
"""Aggregate ``result.json`` files into a CSV table and a Markdown report.

Inputs
------
A directory that contains ``<case_id>/result.json`` files (the output of
``run_matrix.py``) and a pricing file (``pricing.json``).

Outputs
-------
- ``results.csv`` next to the report.
- A Markdown report with two tables:
    1. Per-case wall time / vCPU-hours / cost / output size.
    2. Force-sweep aggregates (one row per sweep case).

Cost model
----------
For a single-instance simulation::

    vcpu_hours          = vcpus * (wall_seconds / 3600)
    on_demand_cost_usd  = (wall_seconds / 3600) * pricing.on_demand_per_hour
    spot_cost_usd       = (wall_seconds / 3600) * pricing.spot_per_hour
    ebs_month_usd       = (output_bytes / 1e9) * pricing.ebs_gp3_per_gb_month
    s3_month_usd        = (output_bytes / 1e9) * pricing.s3_standard_per_gb_month

For a force sweep the runner already includes its own children's wall time in the
single ``wall_seconds`` figure (because ``Force_Sweep.py`` is the parent). The
``sweep_subjobs`` field tells us how many independent jobs ran. Cost numbers
above already reflect the actual instance you ran on.

Examples
--------
::

    python benchmarks/scripts/summarize.py \\
        --results-dir benchmarks/results/aws \\
        --pricing benchmarks/pricing.json \\
        --output benchmarks/results/aws/report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


CSV_COLUMNS = [
    "case_id", "tier", "mode", "pdb_id", "n_residues",
    "duration", "frame_interval", "n_replicas", "omp_threads",
    "instance_assumed", "vcpus", "ram_gib",
    "wall_seconds", "wall_minutes",
    "cpu_user_seconds", "cpu_sys_seconds",
    "peak_rss_mb",
    "output_mb", "output_bytes",
    "steps_per_second", "seconds_per_1M_steps",
    "vcpu_hours",
    "on_demand_per_hour_usd", "spot_per_hour_usd",
    "on_demand_cost_usd", "spot_cost_usd",
    "ebs_month_usd", "s3_month_usd",
    "sweep_subjobs",
    "ok", "exit_code", "host", "started_at", "finished_at",
]


def load_pricing(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text())


def lookup_instance(pricing: dict, region: str, instance: str | None) -> dict[str, float]:
    region_table = pricing.get(region) or {}
    if not instance or instance not in region_table:
        return {"vcpu": 0, "ram_gib": 0.0, "on_demand_per_hour": 0.0, "spot_per_hour": 0.0}
    return region_table[instance]


def row_for_result(result: dict, pricing: dict, region: str) -> dict[str, Any]:
    case = result.get("case", {}) or {}
    instance = case.get("instance_assumed")
    inst_price = lookup_instance(pricing, region, instance)
    vcpus = inst_price.get("vcpu", 0)
    ram = inst_price.get("ram_gib", 0.0)
    od = inst_price.get("on_demand_per_hour", 0.0)
    spot = inst_price.get("spot_per_hour", 0.0)

    wall = float(result.get("wall_seconds", 0.0) or 0.0)
    wall_h = wall / 3600.0
    out_bytes = float(result.get("output_bytes", 0) or 0)

    storage = pricing.get("storage", {}) or {}
    ebs_per_gb = float(storage.get("ebs_gp3_per_gb_month", 0.0))
    s3_per_gb = float(storage.get("s3_standard_per_gb_month", 0.0))

    return {
        "case_id": result.get("case_id", "?"),
        "tier": case.get("tier", ""),
        "mode": case.get("mode", ""),
        "pdb_id": case.get("pdb_id", ""),
        "n_residues": result.get("n_residues", 0),
        "duration": case.get("duration", ""),
        "frame_interval": case.get("frame_interval", ""),
        "n_replicas": case.get("n_replicas", ""),
        "omp_threads": case.get("omp_threads", ""),
        "instance_assumed": instance or "",
        "vcpus": vcpus,
        "ram_gib": ram,
        "wall_seconds": round(wall, 2),
        "wall_minutes": round(wall / 60.0, 2),
        "cpu_user_seconds": round(float(result.get("cpu_user_seconds", 0.0) or 0.0), 2),
        "cpu_sys_seconds": round(float(result.get("cpu_sys_seconds", 0.0) or 0.0), 2),
        "peak_rss_mb": round(float(result.get("peak_rss_mb", 0.0) or 0.0), 1),
        "output_mb": round(float(result.get("output_mb", 0.0) or 0.0), 2),
        "output_bytes": int(out_bytes),
        "steps_per_second": round(float(result.get("steps_per_second", 0.0) or 0.0), 1),
        "seconds_per_1M_steps": round(float(result.get("seconds_per_1M_steps", 0.0) or 0.0), 1),
        "vcpu_hours": round(vcpus * wall_h, 4),
        "on_demand_per_hour_usd": od,
        "spot_per_hour_usd": spot,
        "on_demand_cost_usd": round(wall_h * od, 4),
        "spot_cost_usd": round(wall_h * spot, 4),
        "ebs_month_usd": round((out_bytes / 1e9) * ebs_per_gb, 4),
        "s3_month_usd": round((out_bytes / 1e9) * s3_per_gb, 4),
        "sweep_subjobs": result.get("sweep_subjobs", ""),
        "ok": bool(result.get("ok", False)),
        "exit_code": result.get("exit_code", ""),
        "host": result.get("host", ""),
        "started_at": result.get("started_at", ""),
        "finished_at": result.get("finished_at", ""),
    }


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_(no rows)_\n"
    head = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for r in rows:
        body.append("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |")
    return "\n".join([head, sep, *body]) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--pricing", required=True)
    ap.add_argument("--output", required=True, help="Markdown report path")
    ap.add_argument("--region", default="us-east-1")
    return ap.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_dir)
    pricing = load_pricing(Path(args.pricing))

    rows: list[dict[str, Any]] = []
    for case_dir in sorted(p for p in results_dir.iterdir() if p.is_dir()):
        result_path = case_dir / "result.json"
        if not result_path.is_file():
            continue
        try:
            result = json.loads(result_path.read_text())
        except json.JSONDecodeError as exc:
            print(f"Skipping {result_path}: {exc}", file=sys.stderr)
            continue
        rows.append(row_for_result(result, pricing, args.region))

    if not rows:
        print(f"No result.json files found under {results_dir}", file=sys.stderr)
        return 2

    csv_path = Path(args.output).with_name("results.csv")
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Wrote {csv_path}")

    primary_cols = [
        "case_id", "mode", "pdb_id", "n_residues",
        "instance_assumed", "vcpus", "wall_minutes",
        "vcpu_hours", "on_demand_cost_usd", "spot_cost_usd",
        "output_mb", "peak_rss_mb",
        "seconds_per_1M_steps", "ok",
    ]
    sweep_rows = [r for r in rows if r.get("sweep_subjobs")]
    sweep_cols = [
        "case_id", "pdb_id", "instance_assumed", "vcpus",
        "sweep_subjobs", "wall_minutes",
        "on_demand_cost_usd", "spot_cost_usd", "output_mb",
    ]

    total_on_demand = sum(r["on_demand_cost_usd"] for r in rows)
    total_spot = sum(r["spot_cost_usd"] for r in rows)
    total_wall_min = sum(r["wall_minutes"] for r in rows)
    total_output_gb = sum(r["output_mb"] for r in rows) / 1024.0

    md = []
    md.append("# DynaLab Benchmark Report")
    md.append("")
    md.append(f"- Region assumed: `{args.region}`")
    md.append(f"- Cases reported: **{len(rows)}** "
              f"(ok: {sum(1 for r in rows if r['ok'])}, fail: {sum(1 for r in rows if not r['ok'])})")
    md.append(f"- Total compute on-demand cost (this run): **${total_on_demand:.2f}**")
    md.append(f"- Total compute spot cost (this run): **${total_spot:.2f}**")
    md.append(f"- Total wall time (sum across cases): **{total_wall_min:.1f} min**")
    md.append(f"- Total output written: **{total_output_gb:.2f} GB**")
    md.append("")
    md.append("## Per-case results")
    md.append("")
    md.append(md_table(rows, primary_cols))

    if sweep_rows:
        md.append("## Force-sweep aggregates")
        md.append("")
        md.append(md_table(sweep_rows, sweep_cols))

    md.append("## Notes on the cost model")
    md.append("")
    md.append("- Wall time and memory are real measurements from each run.")
    md.append("- Dollar costs use the instance type recorded in each case's "
              "`instance_assumed` field, looked up in `pricing.json`.")
    md.append("- Spot prices fluctuate. Treat the spot column as an "
              "approximate floor.")
    md.append("- Storage cost is monthly; multiply by months retained in EBS or S3.")
    md.append("- A force sweep ran on a single instance with bounded parallelism. "
              "On AWS Batch, wall time would drop to ~max(sub-job time) and total "
              "cost would scale with sub-job count × per-job time.")
    md.append("")

    Path(args.output).write_text("\n".join(md))
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
