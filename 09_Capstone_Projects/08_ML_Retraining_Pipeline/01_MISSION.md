# Project 08 — ML Model Retraining Pipeline

> MLflow + Airflow + scikit-learn | Difficulty: 🟡 Partially Guided | Time: ~5 hours

---

## The Analogy

Imagine a doctor who trained in medical school twenty years ago and has never updated their knowledge. The world changed — new diseases, new drugs, new best practices — but the doctor keeps giving advice based on stale mental models. At some point, the gap between what they learned and current reality causes real harm.

ML models are the same. A fraud detection model trained in January becomes less accurate by March because spending patterns shift. A churn prediction model trained pre-pandemic is useless post-pandemic. This phenomenon is called **model drift** — the world changed, but the model didn't follow.

This pipeline automates the feedback loop that keeps your model current: detect drift → retrain → evaluate → promote if better → notify the team. It is the foundation of **MLOps** (Machine Learning Operations) — the practice of treating model lifecycle the same way software engineers treat CI/CD pipelines.

---

## Mission

Build an Airflow DAG that:

1. **Detects drift**: compares the current production model's AUC against a rolling 7-day window of prediction accuracy
2. **Branches conditionally**: skips retraining if drift is within tolerance; starts the full retrain path if drift exceeds threshold
3. **Retrains**: trains a `RandomForestClassifier` using scikit-learn, logging everything to **MLflow**
4. **Evaluates**: computes AUC on a holdout test set, logs to MLflow
5. **Quality gate**: `ShortCircuitOperator` blocks promotion if AUC falls below the threshold stored in an **Airflow Variable**
6. **Promotes**: transitions the new model to `Production` in the MLflow Model Registry
7. **Notifies**: sends an email summary to the data science team

---

## Skills You Will Practice

| Skill | Where |
|---|---|
| **BranchPythonOperator** | Conditional DAG branching |
| **ShortCircuitOperator** | Quality gate — skip downstream on condition |
| **MLflow autolog** | Automatic parameter/metric logging in Airflow tasks |
| **MLflow Model Registry** | Staging → Production transitions via Python client |
| **Airflow Variables** | Externalizing thresholds from code |
| **EmailOperator** | Sending notifications from a DAG |
| **Task skipping** | Understanding `SKIPPED` vs `FAILED` states |

---

## Prerequisites

Before starting, you should be comfortable with:

- Airflow intermediate: BranchPythonOperator, ShortCircuitOperator, XCom
- scikit-learn: `RandomForestClassifier`, `train_test_split`, `roc_auc_score`
- MLflow concepts: experiments, runs, artifacts, model registry
- Python: `pandas`, type hints, context managers

---

## Acceptance Criteria

You are done when:

- [ ] The DAG runs end-to-end on the "drift detected" path: all 7 tasks green
- [ ] The DAG runs on the "no drift" path: `check_drift` → `skip_retrain` → DAG ends (4 tasks skipped)
- [ ] MLflow UI (localhost:5000) shows a logged run with parameters, AUC metric, and model artifact
- [ ] The model appears in the MLflow Model Registry in `Production` stage
- [ ] An email (or logged email body) is produced by the `notify_team` task

---

## Difficulty: 🟡 Partially Guided

Each step gives you the concept, the function signature, and one or two key implementation hints. You write the logic yourself. Check `src/solution.py` only after genuinely attempting the step.

---

## Files in This Project

| File | Purpose |
|---|---|
| `01_MISSION.md` | This file |
| `02_ARCHITECTURE.md` | DAG graph, MLflow state machine, data flow |
| `03_GUIDE.md` | 7-step partial walkthrough |
| `src/starter.py` | Skeleton with stubs |
| `src/solution.py` | Complete reference |
| `04_RECAP.md` | Summary, concepts, extensions |

---

## 📂 Navigation

⬅️ **Prev:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [09 — Data Warehouse ETL](../09_Data_Warehouse_ETL/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
