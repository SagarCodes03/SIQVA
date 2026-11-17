"""MLOps Guardrail Router, Real-time Drift Detection, and SQLite Telemetry Logger.

Provides:
- GuardrailRouter: Fast inference (< 1 ms), out-of-vocabulary (OOV) drift tracking,
  and prediction confidence monitoring.
- Telemetry logging: Persists every query inference, latency, and drift signals into
  `data/telemetry.sqlite` without external cloud dependencies.
- Active Learning Queue: Queries flagged for low confidence or high OOV drift
  are queued for human review and retraining.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Optional

import joblib
import numpy as np

MODEL_PATH = Path("models/guardrail_prod.joblib")
META_PATH = Path("models/model_metadata.json")
TELEMETRY_DB = Path("data/telemetry.sqlite")


def is_guardrail_enabled() -> bool:
    """Check if MLOps guardrail and telemetry logging are enabled.

    Can be controlled via:
    - Streamlit session state toggle: st.session_state["enable_mlops_guardrail"] (sidebar toggle)
    - Environment variable: SIQVA_MLOPS_GUARDRAIL=0/1
    - SIQVA_ADMIN=1
    """
    # 1. Streamlit session state toggle has highest priority in interactive UI
    try:
        import streamlit as st

        if hasattr(st, "session_state") and "enable_mlops_guardrail" in st.session_state:
            return bool(st.session_state["enable_mlops_guardrail"])
    except Exception:
        pass

    # 2. In non-UI environments (CLI/tests), require SIQVA_ADMIN=1 unless explicitly enabled
    if os.environ.get("SIQVA_ADMIN", "0").strip() != "1":
        return False

    env_val = os.environ.get("SIQVA_MLOPS_GUARDRAIL", "1").strip().lower()
    if env_val in ("0", "false", "no", "off"):
        return False

    return True


class GuardrailRouter:
    """Production guardrail router with calibrated inference and drift detection."""

    def __init__(
        self,
        model_path: Path | str = MODEL_PATH,
        telemetry_db: Path | str = TELEMETRY_DB,
    ) -> None:
        self.model_path = Path(model_path)
        self.telemetry_db = Path(telemetry_db)
        self.pipe = None
        if self.model_path.exists():
            try:
                self.pipe = joblib.load(self.model_path)
            except Exception:
                self.pipe = None
        if is_guardrail_enabled():
            self._init_db()

    def _init_db(self) -> None:
        """Initialize telemetry database table and indices."""
        self.telemetry_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.telemetry_db) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inference_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    predicted_class TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    oov_ratio REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    flagged_for_review INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_telemetry_time ON inference_logs (timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_telemetry_flagged ON inference_logs (flagged_for_review)"
            )

    def predict_and_log(
        self,
        query: str,
        conf_threshold: float = 0.70,
        oov_threshold: float = 0.65,
    ) -> dict[str, Any]:
        """Classify query, compute drift metrics, log to telemetry SQLite, and return route signal."""
        q_clean = query.strip()
        if not q_clean or self.pipe is None or not is_guardrail_enabled():
            return {
                "label": "DATA_QUERY",
                "raw_label": "DATA_QUERY",
                "confidence": 1.0,
                "oov_ratio": 0.0,
                "latency_ms": 0.0,
                "flagged": False,
                "enabled": is_guardrail_enabled(),
            }

        t0 = time.perf_counter()
        probs = self.pipe.predict_proba([q_clean])[0]
        latency_ms = (time.perf_counter() - t0) * 1000.0

        best_idx = int(np.argmax(probs))
        label = str(self.pipe.classes_[best_idx])
        confidence = float(probs[best_idx])

        # Vocabulary Drift (Out-of-Vocabulary token ratio)
        try:
            word_vec = self.pipe.named_steps["features"].transformer_list[0][1]
            tokens = [w.lower() for w in re.findall(r"\b\w+\b", q_clean) if len(w) > 2]
            if tokens:
                known = sum(1 for w in tokens if w in word_vec.vocabulary_)
                oov_ratio = 1.0 - (known / len(tokens))
            else:
                oov_ratio = 0.0
        except Exception:
            oov_ratio = 0.0

        # Flag for Active Learning if confidence is low or vocabulary is unfamiliar
        flagged = int(confidence < conf_threshold or oov_ratio > oov_threshold)

        # Log to local SQLite telemetry
        try:
            with sqlite3.connect(self.telemetry_db) as conn:
                conn.execute(
                    """
                    INSERT INTO inference_logs (
                        timestamp, query_text, predicted_class, confidence, oov_ratio, latency_ms, flagged_for_review
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now(timezone.utc).isoformat(),
                        q_clean,
                        label,
                        round(confidence, 4),
                        round(oov_ratio, 4),
                        round(latency_ms, 3),
                        flagged,
                    ),
                )
        except Exception:
            pass

        return {
            "label": label if not flagged else "FALLBACK_TO_RULES",
            "raw_label": label,
            "confidence": round(confidence, 3),
            "oov_ratio": round(oov_ratio, 3),
            "latency_ms": round(latency_ms, 2),
            "flagged": bool(flagged),
        }


def get_model_metadata(meta_path: Path | str = META_PATH) -> dict[str, Any]:
    """Retrieve production model metadata and quality gate results."""
    p = Path(meta_path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "dataset_version": "unknown",
        "macro_f1": 0.0,
        "latency_ms": 0.0,
        "classes": [],
        "samples": 0,
        "trained_at": "N/A",
    }


def get_telemetry_summary(
    telemetry_db: Path | str = TELEMETRY_DB,
    recent_limit: int = 20,
) -> dict[str, Any]:
    """Query telemetry database for live drift metrics, volume, and active learning queue."""
    path = Path(telemetry_db)
    if not path.exists():
        return {
            "total_queries": 0,
            "avg_confidence": 1.0,
            "avg_oov_ratio": 0.0,
            "avg_latency_ms": 0.0,
            "flagged_count": 0,
            "class_distribution": {},
            "active_learning_queue": [],
        }

    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row

            # Aggregate stats
            cur = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COALESCE(AVG(confidence), 1.0) as avg_conf,
                    COALESCE(AVG(oov_ratio), 0.0) as avg_oov,
                    COALESCE(AVG(latency_ms), 0.0) as avg_lat,
                    COALESCE(SUM(flagged_for_review), 0) as total_flagged
                FROM inference_logs
                """
            )
            row = cur.fetchone()
            total = row["total"] or 0
            avg_conf = float(row["avg_conf"] or 1.0)
            avg_oov = float(row["avg_oov"] or 0.0)
            avg_lat = float(row["avg_lat"] or 0.0)
            flagged = int(row["total_flagged"] or 0)

            # Class breakdown
            cur = conn.execute(
                """
                SELECT predicted_class, COUNT(*) as c
                FROM inference_logs
                GROUP BY predicted_class
                ORDER BY c DESC
                """
            )
            class_dist = {r["predicted_class"]: r["c"] for r in cur.fetchall()}

            # Active Learning Queue (flagged queries for inspection)
            cur = conn.execute(
                """
                SELECT timestamp, query_text, predicted_class, confidence, oov_ratio, latency_ms
                FROM inference_logs
                WHERE flagged_for_review = 1
                ORDER BY id DESC
                LIMIT ?
                """,
                (recent_limit,),
            )
            al_queue = [dict(r) for r in cur.fetchall()]

            return {
                "total_queries": total,
                "avg_confidence": round(avg_conf, 3),
                "avg_oov_ratio": round(avg_oov, 3),
                "avg_latency_ms": round(avg_lat, 2),
                "flagged_count": flagged,
                "class_distribution": class_dist,
                "active_learning_queue": al_queue,
            }
    except Exception:
        return {
            "total_queries": 0,
            "avg_confidence": 1.0,
            "avg_oov_ratio": 0.0,
            "avg_latency_ms": 0.0,
            "flagged_count": 0,
            "class_distribution": {},
            "active_learning_queue": [],
        }

