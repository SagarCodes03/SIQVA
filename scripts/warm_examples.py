#!/usr/bin/env python3
"""Pre-fetch and warm cache for seed examples in data/examples.json (Q10).

Ensures new users experience instant responses for standard queries.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from siqva.pipeline import PipelineStatus, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("warm_examples")


def warm_cache() -> None:
    examples_file = PROJECT_ROOT / "data" / "examples.json"
    if not examples_file.exists():
        logger.error("Examples file not found: %s", examples_file)
        sys.exit(1)

    with open(examples_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    examples = data.get("examples", [])
    logger.info("Found %d seed examples to warm in cache.", len(examples))

    for idx, ex in enumerate(examples, 1):
        q = ex.get("question", "")
        label = ex.get("label", ex.get("id", ""))
        logger.info("[%d/%d] Warming %s: '%s'...", idx, len(examples), label, q)
        t0 = time.perf_counter()
        res = run(question=q, force_refresh=False)
        elapsed = time.perf_counter() - t0

        if res.status == PipelineStatus.SUCCESS and res.card:
            logger.info(
                "SUCCESS in %.2fs: %d rows, %d profiles (hash: %s...)",
                elapsed,
                res.card.row_count,
                res.card.profile_count,
                res.card.data_hash[:8],
            )
        else:
            logger.warning("FAILED in %.2fs: status=%s, msg=%s", elapsed, res.status, res.error_message)


if __name__ == "__main__":
    warm_cache()
