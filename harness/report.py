"""Honest final numbers: baseline vs champion, each over K held-out runs on the same case set and model.
Stored in `reports` for the dashboard/README.  uv run python -m harness.report [--k 3]"""
import argparse
from datetime import datetime, timezone

from harness.db import get_db
from harness.eval import evaluate, matching_runs
from harness.genomes import champion


def summarize(runs: list[dict]) -> dict:
    out = {}
    for k in ("catch_rate", "false_block_rate", "cost_per_case_usd"):
        vals = [r["metrics"][k] for r in runs if r["metrics"].get(k) is not None]
        out[k] = {"mean": round(sum(vals) / len(vals), 3), "min": min(vals), "max": max(vals)} if vals else None
    inj = [r["metrics"]["by_attack"].get("injection", {}).get("catch_rate") for r in runs]
    inj = [v for v in inj if v is not None]
    out["injection_catch"] = {"mean": round(sum(inj) / len(inj), 3), "min": min(inj), "max": max(inj)} if inj else None
    out["runs"], out["n"] = len(runs), runs[0]["metrics"]["n"] if runs else 0
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--fresh", action="store_true", help="ignore earlier runs; evaluate k new runs per genome")
    args = ap.parse_args()
    db = get_db()
    rows = {}
    for gid in ("g-0001", champion(db)["_id"]):
        runs = [] if args.fresh else matching_runs(db, gid, "heldout")
        while len(runs) < args.k:
            runs.append(evaluate(db, gid, "heldout"))
        rows[gid] = summarize(runs[-args.k:])
        rows[gid]["forced"] = sum(r["metrics"].get("forced", 0) for r in runs[-args.k:])
    doc = {"created_at": datetime.now(timezone.utc), "split": "heldout", "k": args.k, "rows": rows}
    db.reports.insert_one(doc)
    for gid, r in rows.items():
        fmt = lambda m: f"{m['mean']:.3f} [{m['min']:.3f}–{m['max']:.3f}]" if m else "—"  # noqa: E731
        print(f"{gid}: catch {fmt(r['catch_rate'])}  false_block {fmt(r['false_block_rate'])}  "
              f"injection {fmt(r['injection_catch'])}  cost/case {fmt(r['cost_per_case_usd'])}  "
              f"(n={r['n']}, runs={r['runs']}, forced={r['forced']})")


if __name__ == "__main__":
    main()
