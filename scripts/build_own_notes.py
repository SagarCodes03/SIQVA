"""Generate code-derived reference notes directly from SIQVA source modules.

Ensures zero documentation drift by importing directly from:
- src/siqva/gazetteer.py (KNOWN_REGIONS)
- src/siqva/capabilities.py (CAPABILITY_PROFILES)
- src/siqva/qc.py (DataMode descriptions and QC filters)
- src/siqva/planner.py (PlanKind decisions)
- src/siqva/floatindex.py and src/siqva/analyzer.py (Sampling parameters and label text)
- src/siqva/spec.py (Supported Intent enum values)

Output:
- knowledge/notes/own_generated.yaml
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

from siqva.capabilities import CAPABILITY_PROFILES
from siqva.floatindex import SAMPLE_DEFAULT, SAMPLE_MAX, SAMPLE_STEPS
from siqva.gazetteer import KNOWN_REGIONS, REGION_ALIASES
from siqva.planner import PlanKind
from siqva.qc import get_mode_description, get_qc_filter_description
from siqva.spec import DataMode, Intent

OUTPUT_PATH = Path("knowledge/notes/own_generated.yaml")


def build_own_notes_data() -> dict:
    """Build structured dictionary from SIQVA python code definitions."""
    # 1. Supported Regions
    regions_list = []
    for reg_name, bbox in KNOWN_REGIONS.items():
        aliases = [alias for alias, canon in REGION_ALIASES.items() if canon == reg_name and alias.lower() != reg_name.lower()]
        regions_list.append({
            "canonical_name": reg_name,
            "bounding_box": {
                "lon_min": float(bbox.lon_min),
                "lon_max": float(bbox.lon_max),
                "lat_min": float(bbox.lat_min),
                "lat_max": float(bbox.lat_max),
            },
            "aliases": sorted(aliases),
        })

    # 2. Capability Table
    capabilities_list = []
    for intent, prof in CAPABILITY_PROFILES.items():
        depth_val = None
        if prof.default_depth is not None:
            depth_val = {
                "min_depth": float(prof.default_depth.min_depth),
                "max_depth": float(prof.default_depth.max_depth),
            }
        capabilities_list.append({
            "intent": intent.value,
            "module_label": prof.label,
            "data_need": prof.data_need.value,
            "default_depth": depth_val,
            "per_profile_only": prof.per_profile_only,
            "description": prof.description,
        })

    # 3. Data Modes and QC Filters
    modes_list = []
    for mode in [DataMode.RESEARCH, DataMode.STANDARD, DataMode.EXPERT]:
        modes_list.append({
            "mode": mode.value,
            "mode_description": get_mode_description(mode),
            "qc_filter_description": get_qc_filter_description(mode),
        })

    # 4. Plan Decisions
    plans_list = [
        {
            "plan": PlanKind.FULL.value,
            "description": "Fetch entire requested dataset directly when estimated rows fit within the single-request ceiling.",
        },
        {
            "plan": PlanKind.CHUNKED.value,
            "description": "Partition multi-month request into individual calendar months up to SIQVA_MAX_CHUNKS with independent Parquet caching.",
        },
        {
            "plan": PlanKind.SAMPLE.value,
            "description": "Select a representative, deterministic space-time stratified sample of profiles for SAMPLE_OK visualization modules.",
        },
        {
            "plan": PlanKind.REFUSE.value,
            "description": "Refuse oversized execution for FULL_REQUIRED modules with actionable, executable alternatives (narrower period, shallower layer, sub-region).",
        },
    ]

    # 5. Sampling Parameters and Label Texts
    sampling_info = {
        "sample_default": SAMPLE_DEFAULT,
        "sample_steps": list(SAMPLE_STEPS),
        "sample_max": SAMPLE_MAX,
        "sample_label_template": "Sample: {k} of {N} profiles in this region and period, selected by space-time grid (max {sample_max}).",
        "sample_notice_policy": "Regional aggregate statistics and physics are strictly suppressed on sample selections; only individual profile tracks and curves are rendered.",
    }

    # 6. Supported Intents
    intents_list = [
        {"intent": i.value, "enum_name": i.name}
        for i in Intent
    ]

    return {
        "metadata": {
            "origin": "generated",
            "source_code_path": "src/siqva/{gazetteer.py, capabilities.py, qc.py, planner.py, floatindex.py, spec.py}",
            "generator_script": "scripts/build_own_notes.py",
        },
        "supported_regions": {
            "origin": "generated",
            "source_code_path": "src/siqva/gazetteer.py",
            "count": len(regions_list),
            "entries": regions_list,
        },
        "capabilities": {
            "origin": "generated",
            "source_code_path": "src/siqva/capabilities.py",
            "count": len(capabilities_list),
            "entries": capabilities_list,
        },
        "data_modes": {
            "origin": "generated",
            "source_code_path": "src/siqva/qc.py",
            "count": len(modes_list),
            "entries": modes_list,
        },
        "plan_decisions": {
            "origin": "generated",
            "source_code_path": "src/siqva/planner.py",
            "count": len(plans_list),
            "entries": plans_list,
        },
        "sampling": {
            "origin": "generated",
            "source_code_path": "src/siqva/floatindex.py, src/siqva/analyzer.py",
            "config": sampling_info,
        },
        "supported_intents": {
            "origin": "generated",
            "source_code_path": "src/siqva/spec.py",
            "count": len(intents_list),
            "entries": intents_list,
        },
    }


def write_own_notes(output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_own_notes_data()
    yaml_text = yaml.dump(data, sort_keys=False, allow_unicode=True)
    header = (
        "# Auto-generated code-derived notes for SIQVA.\n"
        "# Generated directly from source code modules by scripts/build_own_notes.py.\n"
        "# DO NOT EDIT MANUALLY; run 'python scripts/build_own_notes.py' to regenerate.\n\n"
    )
    output_path.write_text(header + yaml_text, encoding="utf-8")
    print(f"Wrote code-derived notes to {output_path}")


if __name__ == "__main__":
    write_own_notes()
