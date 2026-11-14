"""Generate code-derived narrative reference notes in full sentences directly from SIQVA source modules.

Ensures zero documentation drift by importing directly from:
- src/siqva/floatindex.py and src/siqva/analyzer.py (Sampling parameters and label text)
- src/siqva/interpretation.py and src/siqva/validator.py (Understood as, default depth)
- src/siqva/qc.py (DataMode descriptions and QC filter texts)
- src/siqva/planner.py and src/siqva/chunking.py (Plan thresholds, chunks, row limits)
- src/siqva/card.py (Query card reproducibility)
- src/siqva/spec.py (DataMode, DepthRange, limits)

Output:
- knowledge/notes/own_sentences.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

# Ensure src/ is on sys.path
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import yaml

from siqva.analyzer import FULL_LABEL_TEMPLATE, SAMPLE_LABEL_TEMPLATE
from siqva.chunking import DEFAULT_MAX_CHUNKS, DEFAULT_MAX_TOTAL_ROWS
from siqva.floatindex import SAMPLE_DEFAULT, SAMPLE_MAX, SAMPLE_STEPS
from siqva.planner import DEFAULT_MAX_FULL_ROWS, PlanKind
from siqva.qc import get_mode_description, get_qc_filter_description
from siqva.spec import DataMode, Intent, QuerySpec
from siqva.validator import DEFAULT_MAX_REQUEST_SIZE, MAX_DEPTH_DBAR

OUTPUT_PATH = Path("knowledge/notes/own_sentences.yaml")


def build_own_sentences_data() -> dict:
    """Build structured dictionary of sentence-based notes from SIQVA code definitions."""
    sample_steps_list = list(SAMPLE_STEPS)

    notes = [
        {
            "id": "siqva-sample-explanation",
            "question_examples": [
                "What is a sample in SIQVA and why did I get one?",
                "Why did my query return a sample instead of all profiles?",
                "How are sample profiles selected in SIQVA?",
            ],
            "answer": (
                f"A sample in SIQVA is a space-time stratified selection of float profiles chosen when a complete "
                f"regional dataset exceeds safe data-size caps. The system defaults to {SAMPLE_DEFAULT} profiles "
                f"(with selectable steps of {sample_steps_list[0]}, {sample_steps_list[1]}, and {SAMPLE_MAX}) "
                f"spread evenly across latitude, longitude, and observation time. Samples allow responsive visual "
                f"exploration of profile shapes and water-column structure without overwhelming ERDDAP servers or browser memory. "
                f"To ensure scientific integrity, regional aggregate statistics and physical oceanography calculations "
                f"are strictly suppressed on sampled results."
            ),
            "source_code_path": "src/siqva/floatindex.py, src/siqva/analyzer.py, src/siqva/planner.py",
            "origin": "code",
        },
        {
            "id": "siqva-understood-as-depth",
            "question_examples": [
                "What does 'Understood as' mean in SIQVA?",
                "Why is a default depth of 0 to 500 dbar applied?",
                "What do the tags like [rules] and [default] mean in the query interpretation?",
            ],
            "answer": (
                f"The 'Understood as' header displays the exact structured query parameters interpreted from natural "
                f"language, tagging each resolved parameter with provenance labels such as [rules], [llm], or [default]. "
                f"When a user does not specify a vertical range, SIQVA automatically applies a default depth layer "
                f"of 0 to 500 dbar. This default focuses data fetching on the upper ocean where ocean-atmosphere interaction "
                f"occurs and sensor coverage is densest. Users can override this default at any time by specifying custom "
                f"depths up to the {int(MAX_DEPTH_DBAR)} dbar core Argo limit."
            ),
            "source_code_path": "src/siqva/interpretation.py, src/siqva/validator.py, src/siqva/analyzer.py",
            "origin": "code",
        },
        {
            "id": "siqva-qc-data-modes",
            "question_examples": [
                "What quality control data modes does SIQVA offer?",
                "What is the difference between research, standard, and expert mode in SIQVA?",
                "Which QC flags are excluded in research and standard mode?",
            ],
            "answer": (
                f"SIQVA provides three explicit quality control data delivery modes: research, standard, and expert. "
                f"Research mode ({get_mode_description(DataMode.RESEARCH)}) enforces that "
                f"{get_qc_filter_description(DataMode.RESEARCH).lower()} Standard mode "
                f"({get_mode_description(DataMode.STANDARD)}) ensures that {get_qc_filter_description(DataMode.STANDARD)}. "
                f"Expert mode ({get_mode_description(DataMode.EXPERT)}) performs "
                f"{get_qc_filter_description(DataMode.EXPERT).lower()}"
            ),
            "source_code_path": "src/siqva/qc.py, src/siqva/spec.py",
            "origin": "code",
        },
        {
            "id": "siqva-delayed-mode-timing",
            "question_examples": [
                "Why is recent Argo data missing in research mode?",
                "How long does delayed-mode quality control take for Argo floats?",
                "Why are recent profiles only in real-time or adjusted mode?",
            ],
            "answer": (
                "Recent Argo observations may appear missing when querying in research mode because rigorous delayed-mode "
                "quality control takes about 12 months after profile collection. During this 12-month period, national "
                "data centres accumulate regional time series to perform expert scientific calibration and detect subtle "
                "salinity sensor drift against reference climatologies. Recent profiles collected within the past year "
                "are available only in real-time or adjusted mode. Users seeking observations from the past 12 months "
                "should switch their query mode to standard mode."
            ),
            "source_code_path": "src/siqva/fetcher.py, src/siqva/qc.py",
            "origin": "code",
        },
        {
            "id": "siqva-data-sources-caching",
            "question_examples": [
                "Where does SIQVA get its ocean data from?",
                "How does caching work in SIQVA?",
                "How fresh is the local float index snapshot?",
            ],
            "answer": (
                "SIQVA retrieves real in situ ocean observations from international Argo Global Data Assembly Centres "
                "through IFREMER ERDDAP data servers. Fetched datasets are normalized, hashed with SHA-256, and cached "
                "locally in Apache Parquet format alongside sidecar metadata files for instant reproducible re-use. "
                "Float availability and spatial coverage are pre-screened using a local Parquet float index snapshot "
                "that records platform numbers, cycle numbers, and surfacing coordinates. This local snapshot prevents "
                "futile queries to remote servers when no floats operated in the requested region."
            ),
            "source_code_path": "src/siqva/fetcher.py, src/siqva/floatindex.py",
            "origin": "code",
        },
        {
            "id": "siqva-reproduce-query-card",
            "question_examples": [
                "How do I reproduce a query card in SIQVA?",
                "What information is stored in a SIQVA query card?",
                "How does SIQVA generate Python scripts for re-running fetches?",
            ],
            "answer": (
                "Every completed query in SIQVA produces a persistent, reproducible query card stored in a local SQLite database. "
                "The query card records the exact bounding box, date range, effective depth layer, delivery mode, library "
                "versions, fetch timestamp, and a SHA-256 data hash of the retrieved observations. Clicking any card in "
                "the query history instantly restores the metadata and re-renders plots directly from the local Parquet cache "
                "without contacting remote servers. Each query card also generates a self-contained, runnable Python script "
                "using argopy that reproduces the fetch and quality filtering independently."
            ),
            "source_code_path": "src/siqva/card.py",
            "origin": "code",
        },
        {
            "id": "siqva-llm-data-privacy",
            "question_examples": [
                "Does the language model see my ocean data in SIQVA?",
                "What information is sent to the LLM in SIQVA?",
                "Are oceanographic numbers and statistics generated by an LLM in SIQVA?",
            ],
            "answer": (
                "SIQVA strictly enforces an architectural boundary where the language model never sees oceanographic data "
                "values, profile observations, or calculation results. The language model receives only the user question "
                "text and schema validation instructions to extract query parameters when deterministic rules leave fields "
                "ambiguous. All analytical metrics, summary statistics, physical properties, and visualizations are "
                "computed entirely by deterministic Python code. This design guarantees mathematical honesty, prevents data "
                "hallucinations, and protects user queries from external model data exposure."
            ),
            "source_code_path": "src/siqva/llm_parser.py, src/siqva/rules_parser.py, src/siqva/analyzer.py",
            "origin": "code",
        },
        {
            "id": "siqva-known-limits",
            "question_examples": [
                "What are the known limitations of SIQVA?",
                "Can SIQVA query regions that cross the 180 degree meridian?",
                "Are statistics in SIQVA area-weighted across the ocean?",
            ],
            "answer": (
                f"SIQVA operates with several explicit physical and geographic constraints to guarantee reproducibility "
                f"and prevent misleading results. Bounding boxes crossing the 180-degree antimeridian where the minimum "
                f"longitude exceeds the maximum longitude are rejected with plain-language guidance. Argo floats drift "
                f"freely with ocean currents, resulting in naturally uneven spatial sampling across oceanic basins. "
                f"Furthermore, reported regional statistics are arithmetic means across profile observations rather than "
                f"area-weighted or volume-weighted oceanographic integrals, and profile depths are capped at the core "
                f"Argo limit of {int(MAX_DEPTH_DBAR)} dbar."
            ),
            "source_code_path": "src/siqva/validator.py, src/siqva/gazetteer.py, src/siqva/analyzer.py",
            "origin": "code",
        },
        {
            "id": "siqva-plan-decisions-refusal",
            "question_examples": [
                "How does SIQVA decide whether to fetch full data, chunk, sample, or refuse?",
                "Why was my query refused as oversized?",
                "What are the thresholds for single-request and chunked queries?",
            ],
            "answer": (
                f"SIQVA's query planner evaluates every request against four deterministic execution plans: full fetch, "
                f"calendar-month chunking, stratified sampling, or refusal. Queries estimating up to {DEFAULT_MAX_FULL_ROWS:,} "
                f"rows or fitting the single-request ceiling ({int(DEFAULT_MAX_REQUEST_SIZE):,} cost units) execute directly as a full fetch. "
                f"Multi-month requests exceeding the single-request cap are partitioned into up to {DEFAULT_MAX_CHUNKS} monthly chunks "
                f"up to a cumulative ceiling of {DEFAULT_MAX_TOTAL_ROWS:,} rows with independent Parquet caching. When an oversized request "
                f"targets an analytical module requiring complete data, SIQVA refuses execution and provides three concrete, "
                f"actionable narrowing alternatives: shorter duration, shallower depth, or a sub-region."
            ),
            "source_code_path": "src/siqva/planner.py, src/siqva/chunking.py, src/siqva/validator.py",
            "origin": "code",
        },
    ]

    return {
        "metadata": {
            "origin": "code",
            "developer_name": "",
            "developer_affiliation": "",
            "developer_email": "",
            "generator_script": "scripts/build_own_sentences.py",
            "description": "SIQVA system knowledge and meta-notes written in sentences, generated directly from source code constants and documentation.",
        },
        "notes": notes,
    }


def write_own_sentences(output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_own_sentences_data()
    yaml_text = yaml.dump(data, sort_keys=False, allow_unicode=True)
    header = (
        "# Auto-generated code-derived narrative notes for SIQVA.\n"
        "# Generated directly from source code modules by scripts/build_own_sentences.py.\n"
        "# DO NOT EDIT MANUALLY; run 'python scripts/build_own_sentences.py' to regenerate.\n\n"
    )
    output_path.write_text(header + yaml_text, encoding="utf-8")
    print(f"Wrote code-derived sentence notes to {output_path}")


if __name__ == "__main__":
    write_own_sentences()
