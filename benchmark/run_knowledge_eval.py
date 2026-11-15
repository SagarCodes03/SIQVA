#!/usr/bin/env python3
"""Knowledge Evaluation Benchmark (benchmark/run_knowledge_eval.py).

Evaluates SIQVA's knowledge retrieval and refusal engine against knowledge/questions.jsonl.
Reports accuracy per question type (knowledge, refuse, not_in_notes, meta, data) with
the dev switch (SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED) both ON and OFF.

NO LLM calls. Fully deterministic.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys
from typing import Any

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

import siqva.knowledge as k

QUESTIONS_PATH = ROOT_DIR / "knowledge" / "questions.jsonl"
SAMPLE_SIZE_WARNING_THRESHOLD = 30


def load_questions(path: Path = QUESTIONS_PATH, split: str | None = None) -> list[dict[str, Any]]:
    """Load evaluation questions from knowledge/questions.jsonl, optionally filtered by split."""
    if not path.exists():
        raise FileNotFoundError(f"Questions file not found at {path}")

    questions: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            item = json.loads(line_str)
            if split is None or item.get("split", "dev") == split:
                questions.append(item)
    return questions


def evaluate_split(questions: list[dict[str, Any]], dev_switch: bool) -> dict[str, Any]:
    """Run evaluation over questions with dev switch ON or OFF."""
    old_env = os.environ.get("SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED")
    try:
        os.environ["SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED"] = "1" if dev_switch else "0"
        k.reset_knowledge_index()

        type_counts: dict[str, int] = defaultdict(int)
        type_passed: dict[str, int] = defaultdict(int)
        failures: list[dict[str, Any]] = []

        all_entries = {e.id: e for e in k.load_knowledge_entries()}

        for q in questions:
            q_id = q.get("id", "")
            q_text = q.get("question", "")
            q_type = q.get("type", "knowledge")
            expected_nids = q.get("expected_note_ids", [])

            ans = k.answer(q_text)
            type_counts[q_type] += 1

            has_verified_target = any(
                nid in all_entries and all_entries[nid].verified
                for nid in expected_nids
            )

            passed = False
            if q_type == "knowledge":
                if dev_switch or has_verified_target:
                    passed = (ans.kind == "answer" and any(nid in ans.note_ids for nid in expected_nids))
                else:
                    # In production with switch off, unverified notes return not_in_notes
                    passed = (ans.kind == "not_in_notes")

            elif q_type == "refuse":
                passed = (ans.kind in ("refuse", "language"))

            elif q_type == "not_in_notes":
                passed = (ans.kind == "not_in_notes")

            elif q_type == "data":
                passed = (ans.kind == "data")

            elif q_type == "meta":
                if dev_switch:
                    if expected_nids:
                        passed = (ans.kind == "answer" and any(nid in ans.note_ids for nid in expected_nids))
                    else:
                        passed = (ans.kind in ("answer", "not_in_notes"))
                else:
                    # With switch off, unverified notes return not_in_notes
                    passed = (ans.kind in ("answer", "not_in_notes"))

            if passed:
                type_passed[q_type] += 1
            else:
                failures.append({
                    "id": q_id,
                    "type": q_type,
                    "question": q_text,
                    "decision": ans.kind,
                    "returned_note_ids": ans.note_ids,
                    "expected_note_ids": expected_nids,
                    "score": ans.score,
                })

        total = len(questions)
        total_passed = sum(type_passed.values())
        accuracy = (total_passed / total * 100.0) if total > 0 else 0.0

        return {
            "dev_switch": dev_switch,
            "total": total,
            "total_passed": total_passed,
            "accuracy": accuracy,
            "type_counts": dict(type_counts),
            "type_passed": dict(type_passed),
            "failures": failures,
        }
    finally:
        if old_env is None:
            os.environ.pop("SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED", None)
        else:
            os.environ["SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED"] = old_env
        k.reset_knowledge_index()


def print_eval_report(res: dict[str, Any], split_name: str) -> None:
    """Print structured formatted evaluation report table."""
    mode_str = "ON (Unverified Notes Included)" if res["dev_switch"] else "OFF (Production Verified Only)"
    print("\n" + "=" * 70)
    print(f"SIQVA KNOWLEDGE BENCHMARK EVALUATION — SPLIT: {split_name.upper()}")
    print(f"Dev Switch (SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED): {mode_str}")
    print("=" * 70)

    print(f"\n{'Question Type':<16} | {'Total':<6} | {'Passed':<6} | {'Accuracy (%)':<12}")
    print("-" * 50)
    for q_type in sorted(res["type_counts"].keys()):
        cnt = res["type_counts"][q_type]
        p_cnt = res["type_passed"].get(q_type, 0)
        pct = (p_cnt / cnt * 100.0) if cnt > 0 else 0.0
        print(f"{q_type:<16} | {cnt:<6} | {p_cnt:<6} | {pct:>8.1f}%")

    print("-" * 50)
    print(f"{'OVERALL':<16} | {res['total']:<6} | {res['total_passed']:<6} | {res['accuracy']:>8.1f}%\n")

    if res["failures"]:
        print(f"Failures ({len(res['failures'])}):")
        for f in res["failures"]:
            print(f"  - [{f['id']}] ({f['type']}) \"{f['question']}\"")
            print(f"    Decision: {f['decision']} {f['returned_note_ids']} | Score: {f['score']:.2f} | Expected: {f['expected_note_ids']}")
    else:
        print("All questions in this run passed successfully!")

    print("\nNotice: development questions written by the developers; not an independent evaluation")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run knowledge retrieval & refusal benchmark evaluation.")
    parser.add_argument("--split", choices=["dev", "heldout", "all"], default="dev", help="Question split to evaluate (default: dev)")
    parser.add_argument("--switch", choices=["on", "off", "both"], default="both", help="Evaluate with dev switch on, off, or both (default: both)")
    args = parser.parse_args()

    split_filter = None if args.split == "all" else args.split
    try:
        questions = load_questions(split=split_filter)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    if len(questions) < SAMPLE_SIZE_WARNING_THRESHOLD:
        print(
            f"WARNING: Split '{args.split}' contains {len(questions)} questions "
            f"(< {SAMPLE_SIZE_WARNING_THRESHOLD}). Sample size too small for statistical significance!\n",
            file=sys.stderr,
        )

    switches_to_run = []
    if args.switch in ("on", "both"):
        switches_to_run.append(True)
    if args.switch in ("off", "both"):
        switches_to_run.append(False)

    for switch_state in switches_to_run:
        res = evaluate_split(questions, dev_switch=switch_state)
        print_eval_report(res, args.split)

    return 0


if __name__ == "__main__":
    sys.exit(main())
