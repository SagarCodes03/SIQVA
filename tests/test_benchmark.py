"""Tests for benchmark evaluation infrastructure (Q13)."""

import json
from pathlib import Path
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.run_eval import BenchmarkSummary, evaluate_question, run_benchmark


def test_benchmark_questions_schema_and_count():
    bench_file = Path(__file__).resolve().parent.parent / "benchmark" / "questions.jsonl"
    assert bench_file.exists(), "benchmark/questions.jsonl must exist"

    items = []
    with open(bench_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if line:
                item = json.loads(line)
                assert "id" in item, f"Line {idx} missing 'id'"
                assert "question" in item, f"Line {idx} missing 'question'"
                assert "expected_target" in item, f"Line {idx} missing 'expected_target'"
                items.append(item)

    assert len(items) >= 20, f"Expected at least 20 benchmark questions, found {len(items)}"


def test_run_benchmark_evaluation():
    summary = run_benchmark()
    assert isinstance(summary, BenchmarkSummary)
    assert summary.total_questions >= 20
    assert summary.routing_accuracy_pct >= 90.0
    assert summary.field_accuracy_pct >= 85.0
    assert summary.mean_latency_ms < 50.0  # sub-50ms rules latency
    assert "data_fetch" in summary.per_category
    assert "operation" in summary.per_category
    assert "glossary" in summary.per_category
