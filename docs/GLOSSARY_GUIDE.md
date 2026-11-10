# Oceanographic Glossary Contribution Guide

SIQVA adheres to strict scientific reproducibility. All definitions in the glossary are loaded exclusively from `data/glossary.json` and must carry primary peer-reviewed literature citations.

> [!IMPORTANT]
> The system and LLM never invent definitions. Definitions must be verified against published physical oceanography literature prior to insertion. Unverified terms are never presented to users as factual definitions.

---

## 1. Schema for Glossary Entries

Each entry in `data/glossary.json` conforms to the following schema:

```json
{
  "term": "MLD",
  "canonical_name": "Mixed Layer Depth",
  "definition": "The depth below the ocean surface where temperature or density changes by a specified threshold relative to the surface reference value, characterizing the turbulent, well-mixed surface layer.",
  "source": {
    "author": "de Boyer Montégut et al.",
    "year": 2004,
    "title": "Mixed layer depth over the global ocean: An examination of profile data and a profile-based climatology",
    "journal": "J. Geophys. Res., 109, C12003",
    "url_or_doi": "https://doi.org/10.1029/2004JC002378"
  },
  "formula": "ΔT = 0.2 °C or Δσθ = 0.03 kg/m³ relative to 10 dbar reference",
  "aliases": ["mld", "mixed layer", "mixed layer depth"],
  "verified": false
}
```

### Fields

- `term` *(string, required)*: Standard oceanographic acronym or short identifier (e.g. `MLD`, `TCHP`, `SOFAR`, `BLT`).
- `canonical_name` *(string, required)*: Full English scientific name.
- `definition` *(string, required)*: Clear, rigorous definition citing standard physical oceanography conventions.
- `source` *(object, required)*: Primary literature citation containing:
  - `author` *(string, required)*: Primary authors (e.g. "de Boyer Montégut et al.").
  - `year` *(integer or string, required)*: Year of publication (e.g. 2004).
  - `title` *(string, required)*: Full article or monograph title.
  - `journal` *(string, optional)*: Journal name, volume, and article/page numbers.
  - `url_or_doi` *(string, required)*: Permanent URL or DOI (e.g. "https://doi.org/...").
- `formula` *(string, optional)*: Mathematical formulation or parameter criteria.
- `aliases` *(list of strings, required)*: Lowercase synonyms and search phrases for fuzzy matching.
- `verified` *(boolean, default false)*: Whether the entry has been independently verified against literature and approved according to the verification checklist below.

---

## 2. Verification Requirements & Checklist

Entries start with `"verified": false`. While unverified, `lookup_glossary()` returns the term name and the message `"I do not have a verified definition for that term yet"`, preserving the preliminary citation without presenting unverified text as scientific fact.

To transition an entry to `"verified": true`, the contributor and reviewer must complete the following checklist:

- [ ] **Primary Source Verification**: Full bibliographic reference confirmed (primary author, publication year, article title, and journal or publisher).
- [ ] **Resolvable DOI / URL**: DOI or permanent publisher link verified to resolve directly to the published work.
- [ ] **Formula Consistency**: Mathematical formula and thresholds (e.g. 0.2 °C or 0.03 kg/m³) directly match the cited reference.
- [ ] **Unit Dimensions Matching**: Physical units are mathematically dimensionally consistent and follow SI / TEOS-10 conventions (e.g. kg/m³, °C, dbar, m/s).
- [ ] **Domain Expert Sign-off**: Signed off by an oceanographic domain expert or explicitly checked against a standard published physical oceanography textbook (e.g., Talley et al. *Descriptive Physical Oceanography*, Gill *Atmosphere-Ocean Dynamics*, or IOC/SCOR/IAPSO TEOS-10 Manual).

---

## 3. Validation & Testing

After modifying `data/glossary.json`, verify formatting and test resolution:

```bash
pytest -q tests/test_glossary.py
```
