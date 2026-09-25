# FloatChat — Essentials (Setup & Dependencies)

## 1. Prerequisites
- Python 3.10 or higher
- pip
- Git
- 8GB RAM minimum (for Ollama + Llama 3.2)
- Internet connection (for first-time model download)

---

## 2. Install All Dependencies

### Step 1 — Install Ollama (free local LLM)
```bash
# Mac / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows
# Download from https://ollama.com/download

# Pull Llama 3.2 model (free, ~2GB)
ollama pull llama3.2
```

### Step 2 — Install PostgreSQL + PostGIS
```bash
# Ubuntu / Debian
sudo apt install postgresql postgresql-contrib postgis

# Mac
brew install postgresql postgis

# Start PostgreSQL
sudo service postgresql start
```

### Step 3 — Clone and setup project
```bash
git clone https://github.com/yourusername/floatchat.git
cd floatchat
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. Requirements.txt
```
# ARGO data
argopy==0.1.14

# AI / LLM
langchain==0.2.0
langchain-community==0.2.0
ollama==0.2.0

# Vector DB
chromadb==0.5.0
sentence-transformers==3.0.0

# Data processing
pandas==2.2.0
xarray==2024.3.0
numpy==1.26.0

# Database
psycopg2-binary==2.9.9
sqlalchemy==2.0.0

# Visualization
plotly==5.22.0
folium==0.16.0
streamlit-folium==0.20.0

# UI
streamlit==1.35.0

# Utilities
python-dotenv==1.0.0
requests==2.31.0
```

---

## 4. Environment Variables (.env)
```
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=floatchat
DB_USER=postgres
DB_PASSWORD=yourpassword

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# ChromaDB
CHROMA_PERSIST_DIR=./data/chroma

# Cache
CACHE_DIR=./data/cache
CACHE_TTL_HOURS=24

# App
APP_TITLE=FloatChat
MAX_SESSION_MESSAGES=10
TOP_K_RAG_RESULTS=5
```

---

## 5. Database Setup
```bash
# Create database
psql -U postgres -c "CREATE DATABASE floatchat;"
psql -U postgres -d floatchat -c "CREATE EXTENSION postgis;"

# Run schema
psql -U postgres -d floatchat -f db/schema.sql
```

---

## 6. Run the App
```bash
# Make sure Ollama is running
ollama serve

# Run Streamlit app
streamlit run app.py
```

---

## 7. Deploy to Streamlit Cloud (Free)
1. Push code to GitHub
2. Go to share.streamlit.io
3. Connect your GitHub repo
4. Set environment variables in Streamlit secrets
5. Click Deploy — free public URL generated
