"""Tests for benchmark evaluation infrastructure (Q13 & FIX 3)."""

import json
from pathlib import Path
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.run_eval import (
    BenchmarkSummary,
    MIN_STATISTICAL_SPLIT_SIZE,
    SplitMetrics,
    evaluate_question,
    run_benchmark,
)


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
                assert "split" in item, f"Line {idx} missing 'split'"
                assert item["split"] in ("dev", "heldout"), f"Invalid split {item['split']}"
                items.append(item)

    assert len(items) >= 20, f"Expected at least 20 benchmark questions, found {len(items)}"


def test_run_benchmark_evaluation_and_split_reporting():
    summary = run_benchmark()
    assert isinstance(summary, BenchmarkSummary)
    assert summary.total_questions >= 20
    assert summary.routing_accuracy_pct >= 90.0
    assert summary.field_accuracy_pct >= 85.0
    assert summary.mean_latency_ms < 50.0  # sub-50ms rules latency
    assert "data_fetch" in summary.per_category
    assert "operation" in summary.per_category
    assert "glossary" in summary.per_category

    # Verify honest reporting labels
    assert "regression smoke test" in summary.description.lower()
    assert "not an independent evaluation" in summary.description.lower()
    assert "parser-only latency" in summary.latency_label.lower()

    # Verify per-split reporting
    assert "dev" in summary.splits
    dev_split = summary.splits["dev"]
    assert isinstance(dev_split, SplitMetrics)
    assert dev_split.total_questions == summary.total_questions
    assert dev_split.routing_accuracy_pct == summary.routing_accuracy_pct

    # Since dev set has 20 questions (< 30), verify clear warning is emitted
    assert len(summary.warnings) > 0
    assert any("small sample size" in w.lower() for w in summary.warnings)
    assert dev_split.warning is not None
    assert str(MIN_STATISTICAL_SPLIT_SIZE) in dev_split.warning


def test_custom_fixture_with_adequate_split_has_no_warning(tmp_path):
    # Construct a synthetic split with >= 30 questions
    sample_item = {
        "id": "q_meta",
        "split": "heldout",
        "question": "what query did I just run?",
        "expected_target": "meta",
    }
    items = [dict(sample_item, id=f"q_{i}") for i in range(35)]

    fixture_file = tmp_path / "questions_large.jsonl"
    with open(fixture_file, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")

    summary = run_benchmark(questions_file=fixture_file)
    assert summary.total_questions == 35
    assert "heldout" in summary.splits
    assert summary.splits["heldout"].warning is None
    assert len(summary.warnings) == 0
