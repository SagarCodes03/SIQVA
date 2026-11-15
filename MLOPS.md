# SIQVA MLOps Architecture & Workflow

A lightweight, production-grade MLOps pipeline designed for academic evaluation and enterprise reliability without heavy dependencies (zero PyTorch, zero cloud buckets, zero external servers).

---

## 1. Quick Commands

```bash
# 1. Train model, compute SHA-256 data hash, and log to MLflow (< 0.5s)
python scripts/train_guardrail.py

# 2. Run CI/CD automated quality gate (< 1.0s)
pytest tests/test_mlops_gate.py

# 3. Open MLflow Experiment & Model Registry Dashboard
mlflow ui --backend-store-uri sqlite:///mlflow.db
# View at: http://localhost:5000
```

---

## 2. The 5 Lightweight Pillars

| Pillar | How SIQVA Implements It | Storage / Artifact |
| :--- | :--- | :--- |
| **1. Data Versioning** | SHA-256 hash (`hashlib.sha256`) of dataset logged to MLflow per run (replaces heavy DVC). | `data/guardrail_dataset.jsonl` |
| **2. Guardrail Model** | Word + Char-WB TF-IDF fed to `CalibratedClassifierCV(LinearSVC)`. Robust to typos; runs in **0.5 ms**. | `models/guardrail_prod.joblib` (150 KB) |
| **3. Experiment Tracking** | Local embedded SQLite tracking server & registered model `SIQVA_Guardrail`. | `sqlite:///mlflow.db` |
| **4. CI/CD Quality Gate** | Automated pytest gate blocking commits if **Macro F1 < 0.90** or **latency ≥ 5.0 ms**. | `tests/test_mlops_gate.py` |
| **5. Real-Time Drift** | Prediction confidence drift + Out-of-Vocabulary (OOV) ratio logged on every query. | `data/telemetry.sqlite` |

---

## 3. Query Classification & Guardrail Routing

Every query entering the chat dispatcher passes through the guardrail before regex or parsing:

```
User Query
    │
    ▼
[Guardrail Router] (< 1 ms inference)
    ├── If ADVERSARIAL_INJECTION ──► Immediate refusal (blocks prompt injections & SQL attacks)
    ├── If REFUSAL_OUT_OF_SCOPE  ──► Educational refusal (weather forecasts, non-Argo data, medical)
    ├── If KNOWLEDGE_QUERY       ──► Verbatim verified notes (zero LLM hallucinations)
    └── If DATA_QUERY            ──► Standard SIQVA ocean data pipeline
```

*Every inference logs latency, confidence, and OOV ratio into `data/telemetry.sqlite`.*

---

## 4. Active Learning & Drift Monitoring

- **Confidence Drift:** Monitored via calibrated prediction probabilities (`predict_proba`).
- **Vocabulary Drift (OOV):** Calculated as `1.0 - (known_tokens / total_tokens)`.
- **Active Learning Queue:** When `confidence < 0.70` or `oov_ratio > 0.65`, the query is flagged (`flagged_for_review = 1`). These flagged queries appear in the Streamlit UI for review and retraining.

---

## 5. How to Toggle ON / OFF

The guardrail feature can be toggled without restarting the server:

1. **In Streamlit UI:** Use the **"MLflow Guardrail"** toggle in the sidebar or on the **"MLOps & Telemetry"** page.
2. **Via Environment Variable:**
   ```bash
   # Disable guardrail (bypass straight to rules)
   SIQVA_MLOPS_GUARDRAIL=0
   
   # Enable guardrail (default)
   SIQVA_MLOPS_GUARDRAIL=1
   ```

---

## 6. Current Model Metrics

- **Classes:** `DATA_QUERY`, `KNOWLEDGE_QUERY`, `REFUSAL_OUT_OF_SCOPE`, `ADVERSARIAL_INJECTION`
- **Dataset Size:** 228 verified samples
- **Macro F1 Score:** **0.979** (Quality gate requires $\ge 0.90$)
- **Adversarial Injection Precision & Recall:** **1.00 / 1.00**
- **Inference Latency:** **0.51 ms / query** (Quality gate requires $< 5.0\text{ ms}$)

