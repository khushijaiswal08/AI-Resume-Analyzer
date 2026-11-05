"""Evaluate skill extraction against hand-labelled samples.

Usage:  python scripts/run_eval.py [--details] [--min-f1 0.90]

Prints precision / recall / F1 per sample and overall (micro-averaged: totals of true
positives, false positives and false negatives across all samples). With --min-f1, exits
with code 1 when the overall F1 is below the threshold, so CI fails on a regression.
"""

import argparse
import json
import sys
from pathlib import Path

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
    if args.min_f1 is not None:
        f1 = overall_f1(rows)
        if f1 < args.min_f1:
            print(f"\nFAIL: overall F1 {f1:.2f} is below the --min-f1 threshold {args.min_f1:.2f}.")
            return 1
        print(f"\nPASS: overall F1 {f1:.2f} >= {args.min_f1:.2f}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
