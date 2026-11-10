#!/usr/bin/env python3
"""Automated evaluation harness for SIQVA router and hybrid parser (Q13 & FIX 3).

Note: This is a regression smoke test on development questions written by the developers;
it is not an independent evaluation. Latency measures parser-only speed (rules path,
no network, no data fetch).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import sys
import time
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from siqva.gazetteer import KNOWN_REGIONS
from siqva.parser import parse_detailed
from siqva.router import RouteTarget, route

MIN_STATISTICAL_SPLIT_SIZE = 30
LATENCY_LABEL = "parser-only latency (rules path, no network, no data fetch)"
REGRESSION_DISCLAIMER = (
    "Regression smoke test on development questions written by developers; "
    "not an independent evaluation."
)


@dataclass
class SplitMetrics:
    """Metrics calculated for a specific split (e.g. dev, heldout)."""

    split_name: str
    total_questions: int
    routing_correct: int
    routing_accuracy_pct: float
    field_accuracy_pct: float
    mean_latency_ms: float
    warning: Optional[str] = None


@dataclass
class BenchmarkSummary:
    """Consolidated metrics returned by benchmark run."""

    total_questions: int
    routing_correct: int
    routing_accuracy_pct: float
    field_accuracy_pct: float
    mean_latency_ms: float
    per_category: dict[str, dict[str, Any]] = field(default_factory=dict)
    splits: dict[str, SplitMetrics] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    description: str = REGRESSION_DISCLAIMER
    latency_label: str = LATENCY_LABEL


def evaluate_question(item: dict[str, Any], allow_llm: bool = False) -> dict[str, Any]:
    """Evaluate a single benchmark item."""
    q = item["question"]
    expected_target = item.get("expected_target")
    split = item.get("split", "dev")

    t0 = time.perf_counter()
    route_res = route(q)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    target_match = False
    actual_target = route_res.target.value

    # Parse check if data_fetch or clarification
    parsed_spec = None
    parse_outcome = None
    if route_res.target == RouteTarget.DATA_FETCH or expected_target == "clarification":
        parse_outcome = parse_detailed(q, allow_llm=allow_llm)
        parsed_spec = parse_outcome.spec

    if expected_target == "clarification":
        target_match = (
            route_res.target == RouteTarget.CLARIFICATION
            or (parse_outcome is not None and parse_outcome.clarification is not None)
        )
    else:
        target_match = (actual_target == expected_target)

    # Field matching checks
    field_matches: list[bool] = []
    if parsed_spec is not None:
        if "expected_region" in item:
            exp_bbox = KNOWN_REGIONS.get(item["expected_region"])
            field_matches.append(parsed_spec.region == exp_bbox)
        if "expected_dates" in item:
            d_start, d_end = item["expected_dates"]
            field_matches.append(
                parsed_spec.date_range.start.isoformat() == d_start
                and parsed_spec.date_range.end.isoformat() == d_end
            )
        if "expected_variables" in item:
            exp_vars = item["expected_variables"]
            act_vars = [v.value for v in parsed_spec.variables]
            field_matches.append(sorted(exp_vars) == sorted(act_vars))
        if "expected_intent" in item:
            field_matches.append(parsed_spec.intent.value == item["expected_intent"])

    field_acc = (sum(field_matches) / len(field_matches)) if field_matches else (1.0 if target_match else 0.0)

    return {
        "id": item.get("id"),
        "split": split,
        "question": q,
        "expected_target": expected_target,
        "actual_target": actual_target,
        "target_match": target_match,
        "field_accuracy": field_acc,
        "latency_ms": latency_ms,
    }


def run_benchmark(
    questions_file: Optional[Path | str] = None,
    allow_llm: bool = False,
) -> BenchmarkSummary:
    """Run full benchmark evaluation on questions file."""
    path = Path(questions_file) if questions_file is not None else PROJECT_ROOT / "benchmark" / "questions.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Benchmark questions file not found: {path}")

    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    results = [evaluate_question(item, allow_llm=allow_llm) for item in items]

    total = len(results)
    routing_correct = sum(1 for r in results if r["target_match"])
    routing_acc = (routing_correct / total * 100.0) if total else 0.0
    field_acc = (sum(r["field_accuracy"] for r in results) / total * 100.0) if total else 0.0
    mean_lat = (sum(r["latency_ms"] for r in results) / total) if total else 0.0

    # Per-category breakdown
    categories: dict[str, dict[str, Any]] = {}
    for r in results:
        cat = r["expected_target"]
        if cat not in categories:
            categories[cat] = {"count": 0, "correct": 0, "total_lat": 0.0}
        categories[cat]["count"] += 1
        if r["target_match"]:
            categories[cat]["correct"] += 1
        categories[cat]["total_lat"] += r["latency_ms"]

    per_category = {}
    for cat, data in categories.items():
        cnt = data["count"]
        per_category[cat] = {
            "count": cnt,
            "accuracy_pct": round(data["correct"] / cnt * 100.0, 1),
            "mean_latency_ms": round(data["total_lat"] / cnt, 2),
        }

    # Per-split breakdown & sample size warning
    split_groups: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        s_name = r.get("split", "dev")
        split_groups.setdefault(s_name, []).append(r)

    splits: dict[str, SplitMetrics] = {}
    warnings: list[str] = []

    for s_name, s_results in split_groups.items():
        s_count = len(s_results)
        s_correct = sum(1 for r in s_results if r["target_match"])
        s_routing_acc = (s_correct / s_count * 100.0) if s_count else 0.0
        s_field_acc = (sum(r["field_accuracy"] for r in s_results) / s_count * 100.0) if s_count else 0.0
        s_lat = (sum(r["latency_ms"] for r in s_results) / s_count) if s_count else 0.0

        s_warn = None
        if s_count < MIN_STATISTICAL_SPLIT_SIZE:
            s_warn = (
                f"Split '{s_name}' has {s_count} questions (< {MIN_STATISTICAL_SPLIT_SIZE}). "
                "Small sample size has wide confidence intervals; do not interpret as general system accuracy."
            )
            warnings.append(s_warn)

        splits[s_name] = SplitMetrics(
            split_name=s_name,
            total_questions=s_count,
            routing_correct=s_correct,
            routing_accuracy_pct=round(s_routing_acc, 2),
            field_accuracy_pct=round(s_field_acc, 2),
            mean_latency_ms=round(s_lat, 2),
            warning=s_warn,
        )

    return BenchmarkSummary(
        total_questions=total,
        routing_correct=routing_correct,
        routing_accuracy_pct=round(routing_acc, 2),
        field_accuracy_pct=round(field_acc, 2),
        mean_latency_ms=round(mean_lat, 2),
        per_category=per_category,
        splits=splits,
        warnings=warnings,
        description=REGRESSION_DISCLAIMER,
        latency_label=LATENCY_LABEL,
    )


def print_report(summary: BenchmarkSummary) -> None:
    """Pretty-print benchmark results table."""
    print("=" * 76)
    print("SIQVA BENCHMARK EVALUATION REPORT")
    print(f"Notice  : {summary.description}")
    print(f"Latency : {summary.latency_label}")
    print("=" * 76)
    print(f"Total Questions Evaluated : {summary.total_questions}")
    print(f"Routing Accuracy          : {summary.routing_accuracy_pct:.1f}% ({summary.routing_correct}/{summary.total_questions})")
    print(f"Field Extraction Accuracy : {summary.field_accuracy_pct:.1f}%")
    print(f"Mean Latency (parser-only): {summary.mean_latency_ms:.2f} ms")

    if summary.warnings:
        print("-" * 76)
        print("SAMPLE SIZE WARNINGS:")
        for w in summary.warnings:
            print(f"  [!] {w}")

    print("-" * 76)
    print("PER-SPLIT BREAKDOWN:")
    print(f"{'Split':<12} {'Count':<8} {'Routing Acc':<16} {'Field Acc':<14} {'Mean Latency':<12}")
    print("-" * 76)
    for s_name, sm in summary.splits.items():
        print(
            f"{s_name:<12} {sm.total_questions:<8} {sm.routing_accuracy_pct:>5.1f}%{'':<10} "
            f"{sm.field_accuracy_pct:>5.1f}%{'':<8} {sm.mean_latency_ms:>6.2f} ms"
        )

    print("-" * 76)
    print("PER-CATEGORY BREAKDOWN:")
    print(f"{'Category':<18} {'Count':<8} {'Routing Accuracy':<20} {'Mean Latency':<12}")
    print("-" * 76)
    for cat, metrics in summary.per_category.items():
        print(f"{cat:<18} {metrics['count']:<8} {metrics['accuracy_pct']:>5.1f}%{'':<14} {metrics['mean_latency_ms']:>6.2f} ms")
    print("=" * 76)


if __name__ == "__main__":
    summary = run_benchmark()
    print_report(summary)
