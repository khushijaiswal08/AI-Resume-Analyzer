"""Evaluate skill extraction against hand-labelled samples.

Usage:  python scripts/run_eval.py [--details] [--min-f1 0.90]

Part 1 prints precision / recall / F1 per sample and overall (micro-averaged: totals of true
positives, false positives and false negatives across all samples).
Part 2 runs the v2 layers (bullets, ATS parse-ability, JD match, readiness) on the samples plus
a weak and a messy fictional resume and checks the bounds in evals/quality_expected.json:
the layers must score the strong resumes high and the weak/messy ones low.
With --min-f1, exits with code 1 when the overall F1 is below the threshold; it also exits
with 1 when a quality check fails, so CI fails on a regression of either part.
"""

import argparse
import json
import sys
from pathlib import Path

from resume_analyzer.service import analyze_text
from resume_analyzer.skills import extract_skills, flatten

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "evals"


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Precision, recall and F1, defined as 0.0 when the denominator is 0."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def evaluate(eval_dir: Path = EVAL_DIR) -> list[dict]:
    """Return one row per sample with counts, metrics and the differing skills."""
    expected: dict[str, list[str]] = json.loads(
        (eval_dir / "expected.json").read_text(encoding="utf-8")
    )["samples"]
    rows = []
    for name, labels in expected.items():
        text = (eval_dir / "samples" / name).read_text(encoding="utf-8")
        predicted = set(flatten(extract_skills(text)))
        gold = set(labels)
        tp, fp, fn = len(predicted & gold), len(predicted - gold), len(gold - predicted)
        rows.append(
            {
                "sample": name,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "metrics": prf(tp, fp, fn),
                "false_positives": sorted(predicted - gold),
                "false_negatives": sorted(gold - predicted),
            }
        )
    return rows


def overall_f1(rows: list[dict]) -> float:
    """Micro-averaged F1 across all samples."""
    tp, fp, fn = (sum(row[key] for row in rows) for key in ("tp", "fp", "fn"))
    return prf(tp, fp, fn)[2]


def print_table(rows: list[dict], details: bool) -> None:
    """Print a fixed-width results table."""
    header = f"{'sample':<34}{'TP':>4}{'FP':>4}{'FN':>4}{'precision':>11}{'recall':>8}{'F1':>7}"
    print(header)
    print("-" * len(header))
    for row in rows:
        p, r, f = row["metrics"]
        print(
            f"{row['sample']:<34}{row['tp']:>4}{row['fp']:>4}{row['fn']:>4}"
            f"{p:>11.2f}{r:>8.2f}{f:>7.2f}"
        )
    tp, fp, fn = (sum(row[key] for row in rows) for key in ("tp", "fp", "fn"))
    p, r, f = prf(tp, fp, fn)
    print("-" * len(header))
    print(f"{'OVERALL (micro)':<34}{tp:>4}{fp:>4}{fn:>4}{p:>11.2f}{r:>8.2f}{f:>7.2f}")
    print(f"\n{len(rows)} synthetic samples. Labels: evals/expected.json")
    if details:
        for row in rows:
            print(f"\n{row['sample']}")
            print(f"  false positives: {', '.join(row['false_positives']) or '-'}")
            print(f"  false negatives: {', '.join(row['false_negatives']) or '-'}")


def evaluate_quality(eval_dir: Path = EVAL_DIR) -> list[dict]:
    """Run the full pipeline (no LLM) on each quality sample and check its sanity bounds.

    Each row has the measured numbers and `failures`, a list of human-readable problems.
    """
    expected = json.loads((eval_dir / "quality_expected.json").read_text(encoding="utf-8"))
    rows = []
    for name, bounds in expected["samples"].items():
        text = (eval_dir / name).read_text(encoding="utf-8")
        jd = (eval_dir / bounds["jd"]).read_text(encoding="utf-8") if "jd" in bounds else None
        result = analyze_text(text, jd)
        measured = {
            "ats": result.ats_score.total,
            "bullet_avg": result.bullets.average_score,
            "parse": result.ats_checks.score,
            "readiness": result.readiness.score,
            "jd_weighted": result.jd_analysis.weighted_percent if result.jd_analysis else None,
        }
        failures = []
        for key, bound in bounds.items():
            if key.endswith(("_min", "_max")):
                metric, kind = key.rsplit("_", 1)
                value = measured[metric]
                bad = value is None or (value < bound if kind == "min" else value > bound)
                if bad:
                    failures.append(f"{metric}={value} violates {kind} {bound}")
        statuses = {item.id: item.status for item in result.ats_checks.items}
        for check_id in bounds.get("non_pass", []):
            if statuses.get(check_id) == "pass":
                failures.append(f"ATS check '{check_id}' should not pass")
        rows.append({"sample": name, "measured": measured, "failures": failures})
    return rows


def quality_failures(rows: list[dict]) -> list[str]:
    """All failed checks, including the cross-sample rule: strong resumes beat the weak one."""
    problems = [f"{row['sample']}: {text}" for row in rows for text in row["failures"]]
    by_name = {row["sample"].split("/")[-1]: row["measured"] for row in rows}
    weak = by_name.get("weak_pat_generic.txt")
    for name, measured in by_name.items():
        if weak and name.startswith(("ada", "bruno", "carla", "dev")):
            for key in ("ats", "bullet_avg", "readiness"):
                if (
                    weak[key] is not None
                    and measured[key] is not None
                    and weak[key] >= measured[key]
                ):
                    problems.append(f"weak resume does not score below {name} on {key}")
    return problems


def print_quality(rows: list[dict]) -> None:
    """Print the v2 layer scores per sample."""
    header = f"{'sample':<34}{'ATS':>5}{'bullets':>9}{'parse':>7}{'JD%':>6}{'ready':>7}  checks"
    print()
    print("v2 layers (no LLM)")
    print(header)
    print("-" * len(header))
    for row in rows:
        m = row["measured"]
        fmt = lambda v: "-" if v is None else str(v)  # noqa: E731
        status = "ok" if not row["failures"] else "FAIL"
        print(
            f"{row['sample'].split('/')[-1]:<34}{m['ats']:>5}{fmt(m['bullet_avg']):>9}"
            f"{m['parse']:>7}{fmt(m['jd_weighted']):>6}{m['readiness']:>7}  {status}"
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 if the overall F1 is below --min-f1, else 0."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--details", action="store_true", help="List FP/FN skills per sample.")
    parser.add_argument(
        "--min-f1",
        type=float,
        default=None,
        help="Fail (exit code 1) if the overall F1 is below this value, e.g. 0.90.",
    )
    args = parser.parse_args(argv)
    rows = evaluate()
    print_table(rows, args.details)
    quality = evaluate_quality()
    print_quality(quality)
    problems = quality_failures(quality)
    for problem in problems:
        print(f"QUALITY FAIL: {problem}")
    if args.min_f1 is not None:
        f1 = overall_f1(rows)
        if f1 < args.min_f1:
            print(f"\nFAIL: overall F1 {f1:.2f} is below the --min-f1 threshold {args.min_f1:.2f}.")
            return 1
        print(f"\nPASS: overall F1 {f1:.2f} >= {args.min_f1:.2f}.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
