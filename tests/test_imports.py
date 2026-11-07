"""Test importing all modules across src/siqva and app."""

import importlib
from pathlib import Path
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MODULES = [
    "siqva",
    "siqva.spec",
    "siqva.validator",
    "siqva.gazetteer",
    "siqva.rules_parser",
    "siqva.llm_parser",
    "siqva.parser",
    "siqva.interpretation",
    "siqva.fetcher",
    "siqva.followup",
    "siqva.qc",
    "siqva.analyzer",
    "siqva.physics",
    "siqva.plots",
    "siqva.card",
    "siqva.chunking",
    "siqva.comparison",
    "siqva.glossary",
    "siqva.operations",
    "siqva.pipeline",
    "siqva.router",
    "app",
    "app.ui",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_import_every_module(module_name: str):
    """Proves every module in the project imports cleanly."""
    mod = importlib.import_module(module_name)
    assert mod is not None
