# ArgoCard (FloatChat-R)

ArgoCard translates natural-language oceanographic questions into validated, QC-explicit query specifications (`QuerySpec`), fetches real Argo telemetry data, renders standard plots, and provides reproducible query cards.

## Spec Architecture & Hashing

- **`QuerySpec`**: A validated Pydantic model defining `region` (`lon_min`, `lon_max`, `lat_min`, `lat_max`), `date_range` (`start`, `end`), `variables` (`TEMP`, `PSAL`, `PRES`), optional `depth_range`, `mode` (`research` | `standard` | `expert`), and `intent` (`profile` | `map` | `ts` | `trend`).
- **`spec_hash()`**: SHA-256 hash computed over the full, normalized canonical JSON representation (including `intent`). Uniquely identifies the card and visualization.
- **`fetch_key()`**: SHA-256 hash computed over the normalized data-fetching parameters (`region`, `date_range`, `depth_range`, `variables`, and `mode`), excluding `intent`. This allows queries requesting different visual outputs (e.g. a depth profile vs. a trajectory map) over the exact same data slice to reuse the same cached Parquet dataset.

## Known Limitations

1. **No Antimeridian-Crossing Regions**:
   - Bounding boxes are strictly validated on standard Cartesian longitude ranges: `-180.0 <= lon_min <= lon_max <= 180.0`.
   - Regions crossing the 180° antimeridian (where `lon_min > lon_max` across the date line) are currently not supported and will be rejected by the validator.
2. **Untuned Size Cap Placeholder**:
   - The query size cap is currently calculated using a simple rectangular bounding box area multiplied by the temporal duration in days:
     $$\text{Request Size} = (\text{lon\_max} - \text{lon\_min}) \times (\text{lat\_max} - \text{lat\_min}) \times \text{days}$$
   - This value is an untuned placeholder expressed in $\text{degree}^2 \times \text{days}$ (default threshold: `100,000.0`). It does not account for latitude-dependent convergence of meridians (spherical surface area) or float density variations across ocean basins.

