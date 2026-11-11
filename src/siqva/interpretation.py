"""Pure formatting for displaying the parser's interpretation of a query."""

from __future__ import annotations

from collections.abc import Mapping

from .parser import UnderstoodQuery


def _source_label(provenance: Mapping[str, str], field: str) -> str:
    """Return the stable source label for one interpreted field."""
    source = provenance.get(field, "unresolved")
    if source.startswith("rules"):
        return "rules"
    if source.startswith("llm"):
        return "LLM"
    if source == "default":
        return "default"
    return source


def format_understood_as(understood: UnderstoodQuery, provenance: Mapping[str, str]) -> str:
    """Format a one-line, deterministic description of fields resolved by parsing."""
    parts: list[str] = []

    if understood.region is not None:
        box = understood.region
        region_name = understood.region_name or "coordinates"
        parts.append(
            "Region: "
            f"{region_name} (box [{box.lon_min:.2f}, {box.lon_max:.2f}, "
            f"{box.lat_min:.2f}, {box.lat_max:.2f}]) "
            f"[{_source_label(provenance, 'region')}]"
        )
    elif getattr(understood, "basin", None) is not None:
        parts.append(
            f"Basin: {understood.basin} [{_source_label(provenance, 'region')}]"
        )
    if understood.date_range is not None:
        parts.append(
            f"Dates: {understood.date_range.start.isoformat()} to "
            f"{understood.date_range.end.isoformat()} "
            f"[{_source_label(provenance, 'date_range')}]"
        )
    if understood.variables:
        variables = ", ".join(variable.value for variable in understood.variables)
        parts.append(f"Variables: {variables} [{_source_label(provenance, 'variables')}]")
    if understood.depth_range is not None:
        depth_source = _source_label(provenance, "depth_range")
        default_note = " (default)" if depth_source == "default" else ""
        parts.append(
            f"Depth: {understood.depth_range.min_depth:g}\u2013"
            f"{understood.depth_range.max_depth:g} dbar{default_note} [{depth_source}]"
        )
    if understood.mode is not None:
        parts.append(f"Mode: {understood.mode.value} [{_source_label(provenance, 'mode')}]")
    if understood.intent is not None:
        parts.append(f"Intent: {understood.intent.value} [{_source_label(provenance, 'intent')}]")

    return "Understood as: " + ("; ".join(parts) if parts else "no query fields resolved.")
