# FloatChat — Product Requirements Document (PRD)

## 1. Project Overview
FloatChat is an AI-powered conversational interface that allows non-technical users to explore, query, and visualize real-time ARGO ocean float data using plain English. It replaces the need for Python, NetCDF expertise, or oceanographic knowledge.

---

## 2. Problem Statement
ARGO ocean data is freely available but technically inaccessible. Existing AI chatbots built for this purpose suffer from:
- NL2SQL generating semantically wrong SQL queries
- QC flags being ignored — bad sensor data shown as valid
- No live ARGO API connection — static file uploads only
- Hallucination of float data (wrong ocean, fabricated dates)

---

## 3. Target Users
| User | Need |
|---|---|
| Ocean Scientists (INCOIS) | Fast data retrieval without coding |
| Students / Researchers | Thesis data without argopy expertise |
| Policymakers | Understand ocean trends for decisions |
| Weather Forecasters | Ocean state for model initialization |
| Fisheries Managers | Current and temperature by region |

---

## 4. Core Features

### 4.1 Must Have (MVP)
- [ ] Natural language chat interface
- [ ] Live ARGO data fetch via argopy + Argovis API
- [ ] QC flag filtering (keep flag 1 and 2 only)
- [ ] Template-based query engine (no raw NL2SQL)
- [ ] Depth profile chart (temperature vs depth)
- [ ] Salinity profile chart
- [ ] Float position map
- [ ] Data provenance shown (WMO, lat, lon, date, QC status)
- [ ] Session memory (conversation history)
- [ ] Query validator (reject non-ocean queries)

### 4.2 Should Have
- [ ] T-S (Temperature-Salinity) diagram
- [ ] Time series chart
- [ ] CSV data export
- [ ] Chart export as PNG
- [ ] Fallback handler for unmatched queries

### 4.3 Nice to Have (Future Scope)
- [ ] BGC-Argo support (O2, pH, nitrate)
- [ ] Float trajectory animation
- [ ] Multi-float comparison
- [ ] Voice input
- [ ] Multilingual support

---

## 5. Query Templates (Core Logic)
The LLM must ONLY fill parameters into these templates — never generate raw SQL:

```
1. temp_by_region(lat_min, lat_max, lon_min, lon_max, date_start, date_end)
2. salinity_by_float(wmo_id, depth_min, depth_max)
3. profile_by_date(date, lat, lon, radius_km)
4. float_trajectory(wmo_id, date_start, date_end)
5. param_by_depth(parameter, depth, region, date)
```

---

## 6. QC Flag Rules
Applied automatically before EVERY response:
- Flag 1 → KEEP (good data)
- Flag 2 → KEEP (probably good)
- Flag 3 → DROP (probably bad)
- Flag 4 → DROP (bad data)
- Flag 9 → DROP (missing)

---

## 7. Data Provenance (Every Answer Must Show)
- Float WMO number
- Latitude and Longitude
- Date and time of profile (UTC)
- QC status of measurements used
- Data source (Argovis / ERDDAP)

---

## 8. Non-Functional Requirements
- **Cost:** Zero — all tools must be free and open source
- **Performance:** Response within 10 seconds for standard queries
- **Deployment:** Public URL via Streamlit Community Cloud
- **Reliability:** No hallucinated data — all answers grounded in RAG
- **Scalability:** Handle Indian Ocean region dataset as minimum

---

## 9. Out of Scope
- BGC-Argo parameters (future scope)
- Deep Argo floats (>2000m)
- Real-time streaming data
- Mobile app
- User authentication / login
