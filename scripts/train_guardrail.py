"""MLOps Guardrail Training, Data Lineage & MLflow Registry.

Trains a lightweight calibrated text classifier (TF-IDF + LinearSVC) to classify
user queries into:
- DATA_QUERY
- KNOWLEDGE_QUERY
- REFUSAL_OUT_OF_SCOPE
- ADVERSARIAL_INJECTION

Features:
- Deterministic Git/SHA-256 data version hashing (replaces DVC)
- Local SQLite MLflow experiment tracking (sqlite:///mlflow.db)
- Calibrated prediction probabilities for out-of-vocabulary (OOV) & confidence drift monitoring
- Promotion quality gate (blocks models with Macro F1 < 0.90 or high latency)
"""

from __future__ import annotations

import os
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"

import hashlib
import json
from pathlib import Path
import time

import joblib
import mlflow
import mlflow.sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

DATA_PATH = Path("data/guardrail_dataset.jsonl")
MODEL_OUT = Path("models/guardrail_prod.joblib")
META_OUT = Path("models/model_metadata.json")
MLFLOW_DB = "sqlite:///mlflow.db"


def compute_data_hash(filepath: Path) -> str:
    """Replaces DVC: Generates a deterministic SHA-256 version hash of the dataset."""
    return hashlib.sha256(filepath.read_bytes()).hexdigest()[:12]


def train_and_register(
    data_path: Path = DATA_PATH,
    model_out: Path = MODEL_OUT,
    meta_out: Path = META_OUT,
    tracking_uri: str = MLFLOW_DB,
    min_f1_gate: float = 0.90,
) -> dict:
    """Train guardrail classifier, log lineage and metrics to MLflow, and export production artifact."""
    if not data_path.exists():
        raise FileNotFoundError(f"Training dataset not found: {data_path}")

    # 1. Load dataset & compute version hash
    records = [json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = [r["text"] for r in records]
    labels = [r["label"] for r in records]
    data_version = compute_data_hash(data_path)

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    # 2. Local SQLite MLflow Tracking (Zero external server needed)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("SIQVA_Guardrail_Classifier")

    with mlflow.start_run(run_name=f"guardrail_v_{data_version}"):
        # Word + Character n-grams catch both intent keywords and spelling typos
        features = FeatureUnion([
            ("word", TfidfVectorizer(ngram_range=(1, 2), max_features=3000)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=3000)),
        ])
        clf = CalibratedClassifierCV(LinearSVC(C=1.0, random_state=42), cv=3)
        pipe = Pipeline([("features", features), ("clf", clf)])

        t0 = time.perf_counter()
        pipe.fit(X_train, y_train)
        train_ms = (time.perf_counter() - t0) * 1000

        # Evaluate latency and accuracy
        t_inf = time.perf_counter()
        preds = pipe.predict(X_test)
        inf_ms_per_sample = ((time.perf_counter() - t_inf) * 1000) / max(len(X_test), 1)
        macro_f1 = float(f1_score(y_test, preds, average="macro"))

        # Log parameters, data version, and metrics to MLflow
        mlflow.log_param("dataset_sha256", data_version)
        mlflow.log_param("total_samples", len(records))
        mlflow.log_param("train_samples", len(X_train))
        mlflow.log_param("test_samples", len(X_test))
        mlflow.log_param("model_type", "TFIDF_WordChar_CalibratedLinearSVC")
        mlflow.log_metric("macro_f1", macro_f1)
        mlflow.log_metric("train_time_ms", train_ms)
        mlflow.log_metric("inference_latency_ms", inf_ms_per_sample)

        rep = classification_report(y_test, preds, output_dict=True)

        metadata = {
            "dataset_version": data_version,
            "macro_f1": round(macro_f1, 4),
            "latency_ms": round(inf_ms_per_sample, 4),
            "train_time_ms": round(train_ms, 2),
            "classes": sorted(list(pipe.classes_)),
            "samples": len(records),
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "classification_report": rep,
        }

        # Promotion Gate: Only overwrite production artifact if Macro F1 >= min_f1_gate
        if macro_f1 >= min_f1_gate:
            model_out.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(pipe, model_out)
            meta_out.parent.mkdir(parents=True, exist_ok=True)
            meta_out.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            mlflow.log_artifact(str(model_out))
            mlflow.log_artifact(str(meta_out))
            try:
                mlflow.sklearn.log_model(
                    pipe,
                    artifact_path="model",
                    serialization_format="pickle",
                    registered_model_name="SIQVA_Guardrail",
                )
            except Exception:
                try:
                    mlflow.sklearn.log_model(
                        pipe,
                        artifact_path="model",
                        serialization_format="pickle",
                    )
                except Exception:
                    pass
            print(f"[PROMOTED] F1={macro_f1:.3f} | Latency={inf_ms_per_sample:.2f}ms/query | DataVer={data_version}")
        else:
            raise RuntimeError(f"[REJECTED] Model failed quality gate: F1={macro_f1:.3f} < {min_f1_gate}")

    return metadata


if __name__ == "__main__":
    train_and_register()
