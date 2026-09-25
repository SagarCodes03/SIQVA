# FloatChat — Task List & Implementation Plan

## Phase 1 — Environment Setup (Day 1)
- [ ] Install Python 3.10+, VS Code, Git
- [ ] Install Ollama and pull llama3.2 model
- [ ] Install PostgreSQL + PostGIS
- [ ] Create virtual environment
- [ ] Install all requirements from requirements.txt
- [ ] Create .env file with all variables
- [ ] Run schema.sql to create database tables
- [ ] Verify Ollama running at localhost:11434

## Phase 2 — Data Fetching (Day 2-3)
- [ ] Write fetcher.py using argopy DataFetcher
- [ ] Test fetch by region (lat/lon box)
- [ ] Test fetch by float WMO ID
- [ ] Test fetch by date range
- [ ] Write qc_filter.py — drop flag 3, 4, 9
- [ ] Verify QC filter removes bad measurements
- [ ] Write etl.py — xarray → Pandas → JSON → text chunks
- [ ] Test full fetch → filter → ETL pipeline

## Phase 3 — Storage (Day 3-4)
- [ ] Write db.py — PostgreSQL connection and CRUD
- [ ] Test INSERT profiles into PostgreSQL
- [ ] Test INSERT measurements into PostgreSQL
- [ ] Test clean_measurements VIEW (QC pre-filtered)
- [ ] Set up ChromaDB persistent directory
- [ ] Write rag.py — embed text chunks into ChromaDB
- [ ] Test similarity search returns relevant chunks

## Phase 4 — NL Query Engine (Day 5-7)
- [ ] Write validator.py — ocean-related query check
- [ ] Write intent.py — LLM classifies query type
- [ ] Write templates.py — 5 safe query templates
- [ ] Test template selection for sample queries
- [ ] Test parameter extraction (region, date, WMO, depth)
- [ ] Write fallback handler for unmatched queries
- [ ] Test full NL → template → SQL pipeline

## Phase 5 — RAG + LLM (Day 7-8)
- [ ] Write llm.py — Ollama wrapper with LangChain
- [ ] Write prompt builder — combine SQL + RAG + memory
- [ ] Test grounded answer generation
- [ ] Verify provenance (WMO, lat, lon, date, QC) in output
- [ ] Test session memory across multiple turns

## Phase 6 — UI + Charts (Day 9-10)
- [ ] Write charts.py — Plotly depth profile chart
- [ ] Write charts.py — Plotly T-S diagram
- [ ] Write charts.py — Folium float position map
- [ ] Write charts.py — Plotly time series
- [ ] Write auto chart selector (picks by query intent)
- [ ] Build app.py — Streamlit chat interface
- [ ] Add CSV export button
- [ ] Add PNG chart download button
- [ ] Test full end-to-end flow in UI

## Phase 7 — Testing + Deployment (Day 11-13)
- [ ] Test query: temperature by region
- [ ] Test query: salinity by float WMO ID
- [ ] Test query: depth profile for specific date
- [ ] Test query: float trajectory
- [ ] Test QC filter — compare results with and without
- [ ] Test rejection of non-ocean query
- [ ] Test fallback for unmatched query
- [ ] Push to GitHub
- [ ] Deploy to Streamlit Community Cloud
- [ ] Verify live public URL works
- [ ] Write mini project report
