# SIQVA Knowledge & Query Scope

This document defines the strict operational and informational boundaries for the SIQVA ocean-float question answering system.

---

## 1. What SIQVA Answers

SIQVA provides grounded, deterministic answers for queries falling strictly within these domains:

1. **Argo Observational Data**:
   Queries requesting temperature, salinity, and pressure profiles, float tracks, trajectory maps, T-S diagrams, and acoustic sound speed sections measured by autonomous Argo profiling floats.
2. **Computed Oceanographic Statistics**:
   Deterministic statistical calculations (mean, median, standard deviation, minimum, maximum, count, and temporal/depth differences) computed directly by verified code templates without language model extrapolation.
3. **Verified Knowledge Base Concepts**:
   Oceanographic principles, quality control protocols (real-time vs. delayed-mode), QC flag scales, data mode filtering (R, A, D; research, standard, expert), float engineering mechanics, and TEOS-10 thermodynamic definitions documented in our curated knowledge base notes.

---

## 2. Refusal Categories & Standard Polite Refusal Messages

Queries outside SIQVA's mandate are politely refused without guessing. The standard refusal sentence for each category is defined below:

### Category 1: Forecasts and Future Predictions
- **Scope**: Weather forecasts, future ocean temperature projections, El Niño forecasting, hurricane path predictions.
- **Refusal Sentence**:
  > *"SIQVA cannot provide future weather or climate forecasts; it only analyzes historical and current observations recorded by Argo floats."*

### Category 2: Causal Attribution of Weather and Climate Events
- **Scope**: Explaining why a storm occurred, attributing heatwaves to climate change, or claiming causal mechanisms for regional anomalies.
- **Refusal Sentence**:
  > *"SIQVA does not provide causal attribution or theoretical explanations for specific weather or climate events; it reports observed ocean measurements."*

### Category 3: External Non-Argo Datasets
- **Scope**: Satellite sea surface temperature (SST), atmospheric reanalysis (ERA5, NCEP), surface drifter velocity datasets, numerical ocean model simulations (HYCOM).
- **Refusal Sentence**:
  > *"SIQVA only accesses in situ Argo profiling float data; external datasets such as satellite SST, atmospheric reanalysis, or numerical model outputs are outside our scope."*

### Category 4: Medical and Health Topics
- **Scope**: Medical advice, clinical questions, biological health, human pharmacology.
- **Refusal Sentence**:
  > *"SIQVA is strictly an oceanographic data analysis system and cannot provide medical, clinical, or health advice."*

### Category 5: Non-Ocean General Knowledge Topics
- **Scope**: Politics, general coding tutorials, history, sports, entertainment, economics.
- **Refusal Sentence**:
  > *"SIQVA only answers questions regarding physical oceanography and the international Argo float array; general non-marine topics are not supported."*

### Category 6: Requests for Data Outside the Argo Program
- **Scope**: Shipboard repeat hydrography (GO-SHIP, WOCE), moored tropical arrays (TAO/TRITON/RAMA), marine mammal tags, autonomous gliders.
- **Refusal Sentence**:
  > *"SIQVA queries core and biogeochemical Argo profiling float datasets; observations from non-Argo platforms like gliders, ships, or animal tags are not available."*

---

## 3. "Not in My Notes" Response Policy

When an oceanographic or scientific question pertains to ocean science but is not covered in SIQVA's verified knowledge base notes, the system strictly refuses to invent answers or hallucinate from memory:

> *"I cannot answer this specific question because it is not covered in my verified knowledge notes. Please refer directly to official Argo and TEOS-10 documentation listed in our knowledge manifest."*
