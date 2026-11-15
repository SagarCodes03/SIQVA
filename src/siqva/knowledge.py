"""SIQVA Grounded Knowledge Retrieval Engine (R1).

Loads trusted document notes (knowledge/notes/argo_notes.yaml), code-derived notes
(knowledge/notes/own_sentences.yaml), and literature glossary definitions (data/glossary.json).
Answers concept, operational, and system queries strictly verbatim with provenance citations
from knowledge/manifest.csv, enforces nine deterministic refusal categories, and rejects
uncovered topics with a strict 'not in my notes' statement.

NO LLM calls. NO HTTP network calls. Zero hallucination.
"""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import unicodedata
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
import yaml

# -----------------------------------------------------------------------------
# PATH DEFINITIONS
# -----------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = ROOT_DIR / "knowledge" / "manifest.csv"
ARGO_NOTES_PATH = ROOT_DIR / "knowledge" / "notes" / "argo_notes.yaml"
OWN_SENTENCES_PATH = ROOT_DIR / "knowledge" / "notes" / "own_sentences.yaml"
GLOSSARY_PATH = ROOT_DIR / "data" / "glossary.json"
REFUSAL_CATEGORIES_PATH = ROOT_DIR / "data" / "refusal_categories.json"
SYNONYMS_PATH = ROOT_DIR / "data" / "knowledge_synonyms.json"

# -----------------------------------------------------------------------------
# RETRIEVAL THRESHOLDS (NAMED CONSTANTS)
# -----------------------------------------------------------------------------
BM25_SCORE_THRESHOLD: float = 1.0
MATCHED_QUERY_RATIO_THRESHOLD: float = 0.40
CLOSE_MARGIN_THRESHOLD: float = 0.15

# -----------------------------------------------------------------------------
# DATA MODELS
# -----------------------------------------------------------------------------
class KnowledgeCitation(BaseModel):
    """Citation metadata identifying the verified source document or code path."""

    model_config = ConfigDict(frozen=True)

    source_id: str = ""
    title: str = ""
    version: str = ""
    section_or_page: str = ""
    url_or_doi: str = ""
    retrieved_on: str = ""
    code_paths: list[str] = Field(default_factory=list)


class KnowledgeEntry(BaseModel):
    """Structured knowledge unit loaded from trusted yaml or json sources."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: str  # "document" | "code" | "glossary"
    question_examples: list[str] = Field(default_factory=list)
    answer: str
    aliases: list[str] = Field(default_factory=list)
    limits: Optional[str] = None
    related: list[str] = Field(default_factory=list)
    origin: str  # "document" | "code" | "literature"
    verified: bool = False
    citation: KnowledgeCitation


class KnowledgeAnswer(BaseModel):
    """Deterministic answer produced by the knowledge engine."""

    model_config = ConfigDict(frozen=True)

    kind: str  # "answer" | "not_in_notes" | "refuse" | "greeting" | "language"
    text: str
    citations: list[KnowledgeCitation] = Field(default_factory=list)
    note_ids: list[str] = Field(default_factory=list)
    score: float = 0.0
    status: str = "verified"  # "verified" | "unverified"


# -----------------------------------------------------------------------------
# STOP WORDS & STEMMING RULES
# -----------------------------------------------------------------------------
STOP_WORDS: set[str] = {
    "a", "about", "above", "after", "again", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each",
    "explain", "few", "for", "from", "further", "had", "has", "have", "having", "he",
    "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "itself", "just", "me", "more", "most", "my", "myself",
    "no", "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "please", "same", "she", "should",
    "so", "some", "such", "tell", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
}

PRESERVE_WORDS: set[str] = {
    "is", "as", "ts", "gas", "status", "physics", "this", "yes", "gps", "gsw",
    "ctd", "mld", "ild", "blt", "tchp", "sst", "sss", "argo", "qc", "wmo",
}


def is_include_unverified_enabled() -> bool:
    """Return True if SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED is enabled in the environment."""
    return os.environ.get("SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED", "0").strip().lower() in ("1", "true", "yes")


def light_stem(word: str) -> str:
    """Light rule-based stemming so plurals and common inflections match singular base forms."""
    w = word.lower()
    if w in PRESERVE_WORDS or len(w) <= 3:
        return w

    # -ies -> -y (e.g. anomalies -> anomaly, trajectories -> trajectory)
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"

    # -ing (e.g. profiling -> profile, drifting -> drift, cycling -> cycle)
    if w.endswith("ing") and len(w) > 5:
        stem = w[:-3]
        if stem.endswith(("cycl", "profil", "measur", "surfac", "park")):
            return stem + "e"
        if len(stem) >= 3:
            return stem

    # -ed (e.g. adjusted -> adjust, delayed -> delay, observed -> observe)
    if w.endswith("ed") and len(w) > 4:
        stem = w[:-2]
        if stem.endswith(("observ", "calibr", "measur")):
            return stem + "e"
        if len(stem) >= 3:
            return stem

    # -s (e.g. floats -> float, profiles -> profile, flags -> flag, tests -> test)
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]

    return w


def load_synonyms(path: Path = SYNONYMS_PATH) -> dict[str, str]:
    """Load canonical synonym substitutions from data/knowledge_synonyms.json."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("synonyms", {})
    except Exception:
        return {}


def tokenize_and_normalize(text: str, synonyms: Optional[dict[str, str]] = None) -> list[str]:
    """Lowercase, replace multi-word synonyms, strip punctuation, remove stop words, and stem."""
    if not text:
        return []

    syn_map = synonyms if synonyms is not None else load_synonyms()

    norm_text = text.lower()
    # Normalize unicode to NFKD
    norm_text = unicodedata.normalize("NFKD", norm_text)

    # 1. Multi-word phrase synonym replacement
    for phrase, target in syn_map.items():
        if " " in phrase or "-" in phrase:
            pattern = r"\b" + re.escape(phrase) + r"\b"
            norm_text = re.sub(pattern, f" {target} ", norm_text)

    # 2. Strip non-alphanumeric except underscores
    cleaned = re.sub(r"[^\w\s]", " ", norm_text)

    tokens: list[str] = []
    for raw_tok in cleaned.split():
        tok = raw_tok.strip()
        if not tok or tok in STOP_WORDS:
            continue
        # Check single-word synonym
        canon = syn_map.get(tok, tok)
        stemmed = light_stem(canon)
        # Check synonym of stemmed form
        final_tok = syn_map.get(stemmed, stemmed)
        if final_tok and final_tok not in STOP_WORDS:
            tokens.append(final_tok)

    return tokens


# -----------------------------------------------------------------------------
# MANIFEST AND SOURCES
# -----------------------------------------------------------------------------
def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict[str, str]]:
    """Load knowledge/manifest.csv returning {source_id: manifest_row_dict}."""
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found at {path}")

    sources: dict[str, dict[str, str]] = {}
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("id", "").strip()
            if sid:
                sources[sid] = row
    return sources


def list_sources(manifest_path: Path = MANIFEST_PATH) -> list[dict[str, str]]:
    """Expose registered knowledge sources from manifest.csv.
    
    Returns:
        list[dict[str, str]]: List of dicts containing title, version, retrieved_on,
            licence_as_seen, and link.
    """
    manifest = load_manifest(manifest_path)
    results: list[dict[str, str]] = []
    for sid, row in manifest.items():
        results.append({
            "id": sid,
            "title": row.get("title", ""),
            "version": row.get("version", ""),
            "retrieved_on": row.get("retrieved_on", ""),
            "license_as_seen": row.get("license_as_seen", "unverified"),
            "link": row.get("url_or_doi", ""),
            "status": row.get("status", ""),
            "notes": row.get("notes", ""),
        })
    return results


# -----------------------------------------------------------------------------
# KNOWLEDGE BASE LOADER
# -----------------------------------------------------------------------------
def load_knowledge_entries(
    manifest_path: Path = MANIFEST_PATH,
    argo_notes_path: Path = ARGO_NOTES_PATH,
    own_sentences_path: Path = OWN_SENTENCES_PATH,
    glossary_path: Path = GLOSSARY_PATH,
) -> list[KnowledgeEntry]:
    """Load all knowledge units across documents, own code notes, and glossary.
    
    Cross-checks all document source_ids against manifest.csv.
    """
    manifest = load_manifest(manifest_path)
    entries: list[KnowledgeEntry] = []

    # 1. Document notes (argo_notes.yaml)
    if argo_notes_path.exists():
        with open(argo_notes_path, "r", encoding="utf-8") as f:
            raw_doc_notes = yaml.safe_load(f) or []

        for item in raw_doc_notes:
            note_id = item.get("id", "").strip()
            src_id = item.get("source_id", "").strip()
            if src_id not in manifest:
                raise ValueError(
                    f"Knowledge note '{note_id}' references unknown source_id '{src_id}' not found in manifest.csv"
                )

            m_row = manifest[src_id]
            ver = item.get("source_version") or m_row.get("version", "")
            ret_on = item.get("retrieved_on") or m_row.get("retrieved_on", "")
            cit = KnowledgeCitation(
                source_id=src_id,
                title=m_row.get("title", ""),
                version=ver,
                section_or_page=item.get("section_or_page", ""),
                url_or_doi=m_row.get("url_or_doi", ""),
                retrieved_on=ret_on,
            )

            entry = KnowledgeEntry(
                id=note_id,
                kind="document",
                question_examples=item.get("question_examples", []),
                answer=item.get("answer", "").strip(),
                aliases=item.get("aliases", []),
                limits=item.get("limits"),
                related=item.get("related", []),
                origin="document",
                verified=bool(item.get("verified", False)),
                citation=cit,
            )
            entries.append(entry)

    # 2. Own system code notes (own_sentences.yaml)
    if own_sentences_path.exists():
        with open(own_sentences_path, "r", encoding="utf-8") as f:
            raw_own = yaml.safe_load(f) or {}

        for item in raw_own.get("notes", []):
            note_id = item.get("id", "").strip()
            src_paths_raw = item.get("source_code_path", "")
            code_paths = [p.strip() for p in src_paths_raw.split(",") if p.strip()]

            cit = KnowledgeCitation(
                source_id="siqva-code",
                title="SIQVA System Code & Architecture",
                version="2.0",
                section_or_page=src_paths_raw,
                url_or_doi="",
                retrieved_on="2026-11-14",
                code_paths=code_paths,
            )

            entry = KnowledgeEntry(
                id=note_id,
                kind="code",
                question_examples=item.get("question_examples", []),
                answer=item.get("answer", "").strip(),
                aliases=item.get("aliases", []),
                limits=item.get("limits"),
                related=item.get("related", []),
                origin="code",
                verified=bool(item.get("verified", False)),
                citation=cit,
            )
            entries.append(entry)

    # 3. Scientific glossary (glossary.json)
    if glossary_path.exists():
        try:
            with open(glossary_path, "r", encoding="utf-8") as f:
                raw_gloss = json.load(f)
            for t in raw_gloss.get("terms", []):
                t_term = t.get("term", "").strip()
                t_canon = t.get("canonical_name", "").strip()
                src_meta = t.get("source", {})
                cit_title = src_meta.get("title", t_canon)
                cit_author = src_meta.get("author", "")
                cit_year = str(src_meta.get("year", ""))
                full_title = f"{cit_author} ({cit_year}), {cit_title}" if cit_author else cit_title

                cit = KnowledgeCitation(
                    source_id=f"glossary-{t_term.lower()}",
                    title=full_title,
                    version=cit_year,
                    section_or_page=src_meta.get("journal", ""),
                    url_or_doi=src_meta.get("url_or_doi", ""),
                    retrieved_on="2026-11-14",
                )

                ans_text = t.get("definition", "").strip()
                if t.get("formula"):
                    ans_text += f"\nFormula: {t['formula']}"

                aliases = list(t.get("aliases", []))
                if t_canon.lower() not in [a.lower() for a in aliases]:
                    aliases.append(t_canon.lower())

                entry = KnowledgeEntry(
                    id=t_term.lower(),
                    kind="glossary",
                    question_examples=[f"What is {t_term}?", f"Define {t_canon}"],
                    answer=ans_text,
                    aliases=aliases,
                    limits=None,
                    related=[],
                    origin="literature",
                    verified=bool(t.get("verified", False)),
                    citation=cit,
                )
                entries.append(entry)
        except Exception:
            pass

    return entries


# -----------------------------------------------------------------------------
# BM25 SEARCH ENGINE (PURE PYTHON + SQLITE FTS5 COMPATIBILITY)
# -----------------------------------------------------------------------------
class BM25Index:
    """Okapi BM25 Index with field weighting and synonym expansion."""

    def __init__(self, entries: list[KnowledgeEntry], synonyms: Optional[dict[str, str]] = None):
        self.entries = entries
        self.synonyms = synonyms if synonyms is not None else load_synonyms()
        self.doc_count = len(entries)
        self.k1 = 1.5
        self.b = 0.75

        # Weighted fields per document:
        # id: 3.0, aliases: 3.0, question_examples: 2.5, answer: 1.0
        self.doc_term_freqs: list[dict[str, float]] = []
        self.doc_unique_terms: list[set[str]] = []
        self.doc_lengths: list[float] = []
        self.df: dict[str, int] = {}

        for entry in entries:
            tf: dict[str, float] = {}

            # id tokens
            for tok in tokenize_and_normalize(entry.id, self.synonyms):
                tf[tok] = tf.get(tok, 0.0) + 3.0

            # aliases tokens
            for alias in entry.aliases:
                for tok in tokenize_and_normalize(alias, self.synonyms):
                    tf[tok] = tf.get(tok, 0.0) + 3.0

            # question examples tokens
            for q in entry.question_examples:
                for tok in tokenize_and_normalize(q, self.synonyms):
                    tf[tok] = tf.get(tok, 0.0) + 2.5

            # answer tokens
            for tok in tokenize_and_normalize(entry.answer, self.synonyms):
                tf[tok] = tf.get(tok, 0.0) + 1.0

            self.doc_term_freqs.append(tf)
            unique_terms = set(tf.keys())
            self.doc_unique_terms.append(unique_terms)
            for t in unique_terms:
                self.df[t] = self.df.get(t, 0) + 1

            doc_len = sum(tf.values())
            self.doc_lengths.append(doc_len)

        self.avg_dl = sum(self.doc_lengths) / max(self.doc_count, 1)

    def search(self, query: str, only_verified: bool = True) -> list[tuple[KnowledgeEntry, float, float]]:
        """Search entries returning [(entry, bm25_score, matched_term_ratio)] sorted by score descending."""
        q_tokens = tokenize_and_normalize(query, self.synonyms)
        if not q_tokens:
            return []

        results: list[tuple[KnowledgeEntry, float, float]] = []

        for idx, entry in enumerate(self.entries):
            if only_verified and not entry.verified:
                continue

            tf_doc = self.doc_term_freqs[idx]
            d_len = self.doc_lengths[idx]
            score = 0.0
            matched_terms = 0

            for q_term in set(q_tokens):
                if q_term in tf_doc:
                    matched_terms += 1
                    freq = tf_doc[q_term]
                    n_q = self.df.get(q_term, 0)
                    idf = math.log(((self.doc_count - n_q + 0.5) / (n_q + 0.5)) + 1.0)
                    numerator = freq * (self.k1 + 1.0)
                    denominator = freq + self.k1 * (1.0 - self.b + self.b * (d_len / max(self.avg_dl, 1e-6)))
                    score += idf * (numerator / denominator)

            matched_ratio = matched_terms / len(set(q_tokens))

            # Prioritize direct alias and question example alignment
            q_norm_str = " ".join(q_tokens)
            alias_boost = 0.0
            for alias in entry.aliases:
                alias_norm = " ".join(tokenize_and_normalize(alias, self.synonyms))
                if alias_norm and (q_norm_str == alias_norm or f" {q_norm_str} " in f" {alias_norm} "):
                    alias_boost = max(alias_boost, 2.5)
                    break

            ex_boost = 0.0
            for ex in entry.question_examples:
                ex_norm = " ".join(tokenize_and_normalize(ex, self.synonyms))
                if ex_norm and (q_norm_str == ex_norm or f" {q_norm_str} " in f" {ex_norm} "):
                    ex_boost = max(ex_boost, 1.5)
                    break

            score += alias_boost + ex_boost

            if score > 0.0:
                results.append((entry, score, matched_ratio))

        results.sort(key=lambda x: x[1], reverse=True)
        return results


def check_sqlite_fts5_support() -> bool:
    """Verify that SQLite FTS5 extension is available in the installed SQLite runtime."""
    try:
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute("CREATE VIRTUAL TABLE t_fts_check USING fts5(c);")
        cur.execute("INSERT INTO t_fts_check VALUES ('test');")
        rows = cur.execute("SELECT * FROM t_fts_check WHERE t_fts_check MATCH 'test';").fetchall()
        conn.close()
        return len(rows) > 0
    except Exception:
        return False


# -----------------------------------------------------------------------------
# REFUSAL, GREETING, AND LANGUAGE CLASSIFIERS
# -----------------------------------------------------------------------------
def load_refusal_data(path: Path = REFUSAL_CATEGORIES_PATH) -> dict[str, Any]:
    """Load canonical refusal categories and fixed sentences from data/refusal_categories.json."""
    if not path.exists():
        return {"categories": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"categories": []}


# Category regex triggers mapped to category numbers (1-9)
_CATEGORY_TRIGGERS: list[tuple[int, list[re.Pattern]]] = [
    (
        1,
        [
            re.compile(r"\b(forecast|prediction|will there be|next week|next month|next year|in late 202\d|in 202[7-9]|in 203\d)\b", re.IGNORECASE),
            re.compile(r"\b(will it cause a cyclone|temperature.*be next)\b", re.IGNORECASE),
        ],
    ),
    (
        2,
        [
            re.compile(r"\b(why did cyclone|why did storm|why did hurricane|why did typhoon)\b", re.IGNORECASE),
            re.compile(r"\b(why did .* (?:form|occur|happen) in (?:the )?(?:arabian|bay of bengal|pacific|atlantic))\b", re.IGNORECASE),
            re.compile(r"\b(did global warming (?:directly )?cause|caused by global warming)\b", re.IGNORECASE),
            re.compile(r"\b(directly trigger cyclone|causal attribution for|cause the .* heatwave)\b", re.IGNORECASE),
        ],
    ),
    (
        3,
        [
            re.compile(r"\b(satellite\s+sst|modis|era5|reanalysis|surface drifter|global drifter program|gdp drifter|hycom)\b", re.IGNORECASE),
        ],
    ),
    (
        4,
        [
            re.compile(r"\b(antibiotic|prescribe|prescription|open wound|medical advice|clinical advice|jellyfish sting|vibrio)\b", re.IGNORECASE),
        ],
    ),
    (
        5,
        [
            re.compile(r"\b(poem about|french revolution|world cup|fifa|who won|election|stock market)\b", re.IGNORECASE),
        ],
    ),
    (
        6,
        [
            re.compile(r"\b(woce|go-ship|glider|marine mammal tag|shipboard ctd|bottle data from woce)\b", re.IGNORECASE),
        ],
    ),
    (
        7,
        [
            re.compile(r"\b(ship navigation|marine navigation|search and rescue|voyage planning|navigational hazard)\b", re.IGNORECASE),
        ],
    ),
    (
        8,
        [
            re.compile(r"\b(cod abundance|fish abundance|fish stock|fisheries management|coral reef ecology)\b", re.IGNORECASE),
        ],
    ),
    (
        9,
        [
            re.compile(r"\b(ignore (?:all )?previous instructions|system prompt|reveal internal|override (?:safety|validation))\b", re.IGNORECASE),
        ],
    ),
]

_GREETING_PATTERNS = [
    re.compile(r"^\s*(hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening)\b", re.IGNORECASE),
]

_COURTESY_PATTERNS = [
    re.compile(r"^\s*(thank\s+you|thanks|thx|much\s+appreciated)\b", re.IGNORECASE),
]

_FRENCH_OR_NON_ENGLISH_STARTERS = [
    re.compile(r"^\s*(pouvez-vous|comment|quelle|est-ce\s+que|bonjour|merci)\b", re.IGNORECASE),
    re.compile(r"^\s*(por\s+favor|cómo|mostrar|hola|gracias)\b", re.IGNORECASE),
    re.compile(r"^\s*(bitte|zeigen|wie|danke)\b", re.IGNORECASE),
]


KNOWN_DATA_REGIONS: list[str] = [
    "arabian sea", "bay of bengal", "indian ocean", "north atlantic",
    "mediterranean sea", "mediterranean", "pacific", "nino",
]

KNOWN_DATA_INTENTS: list[str] = [
    "temperature", "salinity", "t-s", "ts", "sound speed", "trend", "profile", "profiles",
]


def is_data_query(text: str) -> bool:
    """Detect whether a question is an observational Argo data visualization/fetch query."""
    tl = text.lower()
    has_region = any(r in tl for r in KNOWN_DATA_REGIONS)
    has_intent = any(i in tl for i in KNOWN_DATA_INTENTS)
    starts_action = any(tl.strip().startswith(a) for a in ["show ", "plot ", "fetch ", "display ", "download "])
    has_year = bool(re.search(r"\b(19\d\d|20\d\d)\b", tl))
    return has_region and (starts_action or (has_intent and has_year))


def is_non_english(text: str) -> bool:
    """Detect non-Latin scripts (Cyrillic, Arabic, Devanagari, Hanzi, etc.) and non-English starter markers."""
    for ch in text:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            if "LATIN" not in name:
                return True
    for pat in _FRENCH_OR_NON_ENGLISH_STARTERS:
        if pat.search(text):
            return True
    return False


def match_refusal(text: str, refusal_data: Optional[dict[str, Any]] = None) -> Optional[tuple[int, str]]:
    """Match query against Category 1-9 refusal triggers, returning (cat_number, refusal_sentence)."""
    data = refusal_data if refusal_data is not None else load_refusal_data()
    categories = data.get("categories", [])
    cat_sentence_map = {c["category_number"]: c["refusal_sentence"] for c in categories}

    for cat_num, patterns in _CATEGORY_TRIGGERS:
        for pat in patterns:
            if pat.search(text):
                sentence = cat_sentence_map.get(cat_num, "")
                return cat_num, sentence

    return None


# -----------------------------------------------------------------------------
# MAIN PUBLIC API: knowledge.answer(question)
# -----------------------------------------------------------------------------
_INDEX_INSTANCE: Optional[BM25Index] = None


def get_knowledge_index() -> BM25Index:
    """Return singleton BM25 search index over all loaded knowledge units."""
    global _INDEX_INSTANCE
    if _INDEX_INSTANCE is None:
        entries = load_knowledge_entries()
        _INDEX_INSTANCE = BM25Index(entries)
    return _INDEX_INSTANCE


def reset_knowledge_index() -> None:
    """Reset the singleton knowledge search index (useful for test resets)."""
    global _INDEX_INSTANCE
    _INDEX_INSTANCE = None


def answer(question: str) -> KnowledgeAnswer:
    """Produce grounded, deterministic knowledge response for user question.
    
    Order of operations:
    1. Rule-based refusal detection for Categories 1-9 from data/refusal_categories.json.
    2. Conversational greetings and thanks from scope.md / refusal_categories.json.
    3. Language rule: non-English queries receive guidance message.
    4. Retrieval: return best entry's verbatim answer with citations when score,
       matched query ratio, and margin pass thresholds.
    5. Fallback: return 'not in my notes' statement.
    """
    q_clean = question.strip()
    refusal_data = load_refusal_data()

    fallback_not_in_notes = refusal_data.get(
        "not_in_notes",
        "I cannot answer this specific question because it is not covered in my verified knowledge notes. "
        "Please refer directly to official Argo and TEOS-10 documentation listed on the app's Sources page.",
    )
    greeting_sentence = refusal_data.get(
        "greeting",
        "Hello! I am SIQVA, an assistant for exploring Argo ocean float data and physical oceanography. How can I help you today?",
    )
    courtesy_sentence = refusal_data.get(
        "courtesy",
        "You are welcome! Let me know if you have more questions about Argo ocean data.",
    )
    language_sentence = refusal_data.get(
        "language",
        "SIQVA currently supports English queries only. Please submit your question about Argo data in English.",
    )

    if not q_clean:
        return KnowledgeAnswer(kind="not_in_notes", text=fallback_not_in_notes)

    # (a) Refusal check (Categories 1-9)
    refusal_match = match_refusal(q_clean, refusal_data)
    if refusal_match:
        cat_num, ref_text = refusal_match
        return KnowledgeAnswer(
            kind="refuse",
            text=ref_text,
            score=1.0,
            status="verified",
        )

    # (b) Greetings and thanks
    for pat in _GREETING_PATTERNS:
        if pat.match(q_clean):
            return KnowledgeAnswer(
                kind="greeting",
                text=greeting_sentence,
                score=1.0,
                status="verified",
            )

    for pat in _COURTESY_PATTERNS:
        if pat.match(q_clean):
            return KnowledgeAnswer(
                kind="greeting",
                text=courtesy_sentence,
                score=1.0,
                status="verified",
            )

    # (c) Language rule
    if is_non_english(q_clean):
        return KnowledgeAnswer(
            kind="language",
            text=language_sentence,
            score=1.0,
            status="verified",
        )

    # (d) Data fetch query check (in-scope data queries route to pipeline, not knowledge)
    if is_data_query(q_clean):
        return KnowledgeAnswer(
            kind="data",
            text="This is an Argo observational data query. Please execute it via the Query Terminal to fetch profiles and render plots.",
            score=1.0,
            status="verified",
        )

    # (e) Retrieval
    index = get_knowledge_index()
    only_verified = not is_include_unverified_enabled()
    search_results = index.search(q_clean, only_verified=only_verified)

    if search_results:
        top_entry, top_score, top_ratio = search_results[0]
        if top_score >= BM25_SCORE_THRESHOLD and top_ratio >= MATCHED_QUERY_RATIO_THRESHOLD:
            # Check for two close entries
            is_close = False
            second_entry: Optional[KnowledgeEntry] = None
            if len(search_results) > 1:
                second_e, score_2, ratio_2 = search_results[1]
                if score_2 >= BM25_SCORE_THRESHOLD and ratio_2 >= MATCHED_QUERY_RATIO_THRESHOLD:
                    margin = (top_score - score_2) / max(top_score, 1e-6)
                    if margin < CLOSE_MARGIN_THRESHOLD:
                        is_close = True
                        second_entry = second_e

            status_val = "unverified" if (not top_entry.verified or (second_entry and not second_entry.verified)) else "verified"

            if is_close and second_entry is not None:
                combined_text = (
                    f"**{top_entry.id}**:\n{top_entry.answer}\n\n"
                    f"**{second_entry.id}**:\n{second_entry.answer}"
                )
                if top_entry.limits:
                    combined_text += f"\n\n*Limits ({top_entry.id})*: {top_entry.limits}"
                if second_entry.limits:
                    combined_text += f"\n\n*Limits ({second_entry.id})*: {second_entry.limits}"

                return KnowledgeAnswer(
                    kind="answer",
                    text=combined_text,
                    citations=[top_entry.citation, second_entry.citation],
                    note_ids=[top_entry.id, second_entry.id],
                    score=top_score,
                    status=status_val,
                )
            else:
                ans_text = top_entry.answer
                if top_entry.limits:
                    ans_text += f"\n\n*Limits*: {top_entry.limits}"

                return KnowledgeAnswer(
                    kind="answer",
                    text=ans_text,
                    citations=[top_entry.citation],
                    note_ids=[top_entry.id],
                    score=top_score,
                    status=status_val,
                )

    # (e) Otherwise: not in notes
    return KnowledgeAnswer(
        kind="not_in_notes",
        text=fallback_not_in_notes,
        score=0.0,
        status="verified",
    )
