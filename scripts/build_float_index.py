"""Build local float index Parquet and JSON sidecar from GDAC ar_index_global_prof.txt.gz.

Usage:
    python scripts/build_float_index.py [path/to/ar_index_global_prof.txt.gz] [--output-dir data]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import logging
from pathlib import Path
import re
from typing import Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Real GDAC index columns:
# file,date,latitude,longitude,ocean,profiler_type,institution,date_update
GDAC_COLUMNS = [
    "file",
    "date",
    "latitude",
    "longitude",
    "ocean",
    "profiler_type",
    "institution",
    "date_update",
]

_FILENAME_RE = re.compile(r"^([DR])(\d+)_(\d+)[A-Z]?\.nc$")


def build_float_index(
    input_path: Path | str,
    output_dir: Path | str = "data",
    max_rows: Optional[int] = None,
) -> tuple[Path, Path]:
    """Parse ar_index_global_prof.txt.gz and write compact float_index.parquet and sidecar JSON.

    Args:
        input_path: Path to ar_index_global_prof.txt.gz.
        output_dir: Output directory for float_index.parquet and float_index.json.
        max_rows: Optional ceiling on rows to parse (useful for tests/quick builds).

    Returns:
        tuple[Path, Path]: (parquet_path, json_path)
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Index archive file not found: {input_file}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "float_index.parquet"
    json_path = out_dir / "float_index.json"

    wmos: list[int] = []
    cycles: list[int] = []
    is_delayed: list[bool] = []
    dates: list[str] = []
    lats: list[float] = []
    lons: list[float] = []
    oceans: list[str] = []
    institutions: list[str] = []

    dropped_count = 0
    row_count = 0

    open_fn = gzip.open if str(input_file).endswith(".gz") else open

    with open_fn(input_file, "rt", encoding="utf-8", errors="replace") as f:
        # Read header / comment lines
        for line in f:
            line_str = line.strip()
            if not line_str.startswith("#"):
                # Column header line
                header_cols = [c.strip() for c in line_str.split(",")]
                break

        # Process data rows
        try:
            for line in f:
                if max_rows is not None and row_count >= max_rows:
                    break

                parts = line.strip().split(",")
                if len(parts) < 5:
                    dropped_count += 1
                    continue

                file_str = parts[0]
                date_str = parts[1]
                lat_str = parts[2]
                lon_str = parts[3]
                ocean_str = parts[4].strip()
                inst_str = parts[6].strip() if len(parts) > 6 else ""

                # Extract WMO and cycle
                fname = file_str.split("/")[-1]
                m = _FILENAME_RE.match(fname)
                if not m:
                    # Fallback extraction
                    path_parts = file_str.split("/")
                    if len(path_parts) >= 2 and path_parts[1].isdigit():
                        wmo_val = int(path_parts[1])
                    else:
                        dropped_count += 1
                        continue
                    delayed_val = fname.startswith("D")
                    # Try cycle from filename
                    cycle_m = re.search(r"_(\d+)", fname)
                    cycle_val = int(cycle_m.group(1)) if cycle_m else 0
                else:
                    mode_char, wmo_s, cycle_s = m.groups()
                    delayed_val = (mode_char == "D")
                    wmo_val = int(wmo_s)
                    cycle_val = int(cycle_s)

                try:
                    lat_val = float(lat_str)
                    lon_val = float(lon_str)
                except ValueError:
                    dropped_count += 1
                    continue

                # Coordinate sanity check
                if not (-90.0 <= lat_val <= 90.0 and -180.0 <= lon_val <= 180.0):
                    dropped_count += 1
                    continue

                wmos.append(wmo_val)
                cycles.append(cycle_val)
                is_delayed.append(delayed_val)
                dates.append(date_str)
                lats.append(lat_val)
                lons.append(lon_val)
                oceans.append(ocean_str)
                institutions.append(inst_str)

                row_count += 1

        except EOFError:
            # Handle truncated archives gracefully
            logger.warning(
                "Reached unexpected EOF in %s at row %d; continuing with read records.",
                input_file,
                row_count,
            )

    if not wmos:
        raise ValueError(f"No valid float profile records parsed from {input_file}")

    # Build DataFrame with compact dtypes
    # Convert dates: format %Y%m%d%H%M%S
    parsed_dates = pd.to_datetime(dates, format="%Y%m%d%H%M%S", errors="coerce")

    df = pd.DataFrame(
        {
            "wmo": np.array(wmos, dtype=np.int32),
            "cycle_number": np.array(cycles, dtype=np.int32),
            "cycle": np.array(cycles, dtype=np.int32),  # alias for backward-compatibility
            "latitude": np.array(lats, dtype=np.float32),
            "longitude": np.array(lons, dtype=np.float32),
            "date": parsed_dates,
            "ocean": pd.Categorical(oceans, categories=["A", "I", "P", ""]),
            "is_delayed": np.array(is_delayed, dtype=bool),
            "institution": pd.Categorical(institutions),
        }
    )

    # Filter any row where date failed parsing
    valid_mask = df["date"].notna()
    if not valid_mask.all():
        dropped_count += int((~valid_mask).sum())
        df = df[valid_mask].reset_index(drop=True)

    df.to_parquet(parquet_path, index=False)

    min_date = df["date"].min().date().isoformat()
    max_date = df["date"].max().date().isoformat()
    build_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    ocean_counts = df["ocean"].value_counts().to_dict()
    # Stringify keys
    ocean_counts = {str(k): int(v) for k, v in ocean_counts.items() if str(k)}

    sidecar = {
        "source_file": input_file.name,
        "build_date": build_ts,
        "row_count": len(df),
        "min_date": min_date,
        "max_date": max_date,
        "dropped_row_count": dropped_count,
        "ocean_counts": ocean_counts,
        "unique_floats": int(df["wmo"].nunique()),
    }

    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(sidecar, jf, indent=2)

    return parquet_path, json_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build float index from GDAC profile directory file")
    parser.add_argument(
        "input",
        nargs="?",
        default="data/raw/ar_index_global_prof.txt.gz",
        help="Path to ar_index_global_prof.txt.gz",
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Directory where float_index.parquet and float_index.json are created",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Limit on rows to parse",
    )
    args = parser.parse_args()

    p_path, j_path = build_float_index(args.input, output_dir=args.output_dir, max_rows=args.max_rows)
    print(f"Successfully generated float index at {p_path} and {j_path}")
