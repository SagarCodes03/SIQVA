# Oceanographic Glossary Contribution Guide

SIQVA adheres to strict scientific reproducibility. All definitions in the glossary are loaded exclusively from `data/glossary.json` and must carry primary peer-reviewed literature citations.

> [!IMPORTANT]
> The system and LLM never invent definitions. Definitions must be verified against published physical oceanography literature prior to insertion.

---

## 1. Schema for Glossary Entries

Each entry in `data/glossary.json` conforms to the following schema:

```json
{
  "term": "MLD",
  "canonical_name": "Mixed Layer Depth",
  "definition": "The depth below the ocean surface where temperature or density changes by a specified threshold relative to the surface reference value, characterizing the turbulent, well-mixed surface layer.",
  "source": "de Boyer Montégut et al. (2004), J. Geophys. Res., 109, C12003",
  "formula": "ΔT = 0.2 °C or Δσθ = 0.03 kg/m³ relative to 10 dbar reference",
  "aliases": ["mld", "mixed layer", "mixed layer depth"]
}
```

### Fields

- `term` *(string, required)*: Standard oceanographic acronym or short identifier (e.g. `MLD`, `TCHP`, `SOFAR`, `BLT`).
- `canonical_name` *(string, required)*: Full English scientific name.
- `definition` *(string, required)*: Clear, rigorous definition citing standard physical oceanography conventions.
- `source` *(string, required)*: Primary literature citation (Author, year, journal, volume, page/doi).
- `formula` *(string, optional)*: Mathematical formulation or parameter criteria.
- `aliases` *(list of strings, required)*: Lowercase synonyms and search phrases for fuzzy matching.

---

## 2. Validation & Testing

After modifying `data/glossary.json`, verify formatting and test resolution:

```bash
pytest -q tests/test_glossary.py
```
