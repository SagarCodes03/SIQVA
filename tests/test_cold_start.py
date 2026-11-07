"""Tests for cold start, seed examples gallery, and non-blocking Ollama warm-up (Q10)."""

import json
from pathlib import Path
import threading
import pytest

from siqva.llm_parser import warmup_ollama_async
from siqva.parser import parse_detailed


def test_examples_json_schema_and_contents():
    examples_path = Path(__file__).resolve().parent.parent / "data" / "examples.json"
    assert examples_path.exists(), "data/examples.json must exist"

    with open(examples_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    examples = data.get("examples", [])
    assert len(examples) >= 4, "Must contain at least 4 seed examples"

    required_keys = {"id", "label", "question", "intent", "region", "date"}
    for ex in examples:
        assert required_keys.issubset(ex.keys()), f"Missing keys in example {ex.get('id')}"
        assert ex["question"].strip(), "Example question cannot be empty"
        assert ex["label"].strip(), "Example label cannot be empty"


def test_seed_examples_are_parseable_by_rules():
    examples_path = Path(__file__).resolve().parent.parent / "data" / "examples.json"
    with open(examples_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for ex in data.get("examples", []):
        outcome = parse_detailed(ex["question"], allow_llm=False)
        assert outcome.spec is not None, f"Seed example '{ex['question']}' failed rules parsing: {outcome.clarification}"
        assert outcome.spec.region is not None
        assert outcome.spec.date_range is not None


def test_warmup_ollama_async_starts_daemon_thread():
    thread = warmup_ollama_async()
    assert isinstance(thread, threading.Thread)
    assert thread.daemon is True
    assert thread.name == "ollama-warmup"


def test_warm_examples_script_syntax():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "warm_examples.py"
    assert script_path.exists(), "scripts/warm_examples.py must exist"

    with open(script_path, "r", encoding="utf-8") as f:
        code = f.read()

    compile(code, str(script_path), "exec")
