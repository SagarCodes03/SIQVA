# FloatChat — Constraints & Design Decisions

## 1. Hard Constraints
| Constraint | Reason |
|---|---|
| Zero cost | Student mini project — no budget |
| No OpenAI API | Paid service — use Ollama instead |
| No Pinecone | Paid — use ChromaDB instead |
| No AWS / GCP | Paid — use Streamlit Cloud instead |
| No raw NL2SQL | Core improvement over existing work |
| QC filtering mandatory | Core improvement over existing work |
| No static .nc files | Core improvement — live API only |

---

## 2. Design Decisions & Why

### Why Ollama + Llama 3.2 instead of GPT-4?
- GPT-4 costs money per API call
- Llama 3.2 runs locally — zero cost forever
- For intent classification and parameter extraction, Llama 3.2 is sufficient
- RAG grounding compensates for smaller model capability

### Why ChromaDB instead of FAISS or Pinecone?
- ChromaDB is the easiest to set up locally
- Persistent storage built in
- Free forever
- FAISS has no persistence by default
- Pinecone is paid

### Why PostgreSQL instead of SQLite?
- PostGIS extension needed for geospatial queries (bbox, radius)
- PostgreSQL handles larger datasets better
- Required for float position mapping by region

### Why templates instead of NL2SQL?
- NL2SQL fails on multi-table joins (proven in CIDR 2024 paper)
- Templates are 100% reliable — LLM only fills parameters
- Easier to debug and test
- Directly addresses documented FloatChat limitation

### Why Streamlit instead of Flask/FastAPI + React?
- Streamlit builds full chat UI in ~20 lines of Python
- No frontend JavaScript needed
- Free deployment on Streamlit Community Cloud
- Sufficient for mini project scope

### Why argopy instead of direct API calls?
- argopy handles Argovis, ERDDAP, FTP, S3 in one interface
- Built-in xarray integration
- Maintained by IFREMER (official ARGO body)
- Handles authentication, retry, and format conversion

---

## 3. Known Limitations (Accepted for Mini Project)
- BGC parameters not supported (future scope)
- Ollama responses slower than cloud LLMs (~3-5 seconds)
- ChromaDB limited to small-medium datasets locally
- No user authentication
- No multi-user session isolation

---

## 4. Improvement Over Existing FloatChats
| Problem in Existing | Our Solution |
|---|---|
| Raw NL2SQL fails | Safe query templates |
| QC flags ignored | Auto QC filter before every response |
| Static file uploads | Live argopy + Argovis API |
| Hallucinated data | RAG grounds all answers |
| No provenance shown | WMO + lat/lon + date + QC in every answer |
| Local only | Streamlit Cloud free deployment |
| No data export | CSV + PNG export added |
