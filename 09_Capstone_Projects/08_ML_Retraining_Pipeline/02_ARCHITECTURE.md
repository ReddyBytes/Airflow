# Project 08 — Architecture

---

## Full DAG Graph

```
DAG: ml_model_retraining_pipeline
Schedule: 0 6 * * *  (daily at 6am)

  ┌─────────────────────┐
  │     check_drift     │  PythonOperator
  │                     │  Compares current model AUC to 7-day rolling mean
  └──────────┬──────────┘
             │
             │  returns branch name via BranchPythonOperator
             ▼
  ┌─────────────────────┐
  │  drift_gate_branch  │  BranchPythonOperator
  │                     │  "retrain_start" OR "skip_retrain"
  └──────┬──────┬───────┘
         │      │
         │      └─────────────────────────────────────────────────┐
         │                                                         │
         ▼                                                         ▼
  ┌──────────────┐                                      ┌──────────────────┐
  │ retrain_start│                                      │  skip_retrain    │
  │ (DummyOp)    │                                      │  (DummyOperator) │
  └──────┬───────┘                                      └──────────────────┘
         │
         ▼
  ┌──────────────┐
  │  train_model │  PythonOperator
  │              │  sklearn RandomForest + MLflow autolog
  └──────┬───────┘
         │
         ▼
  ┌──────────────────┐
  │  evaluate_model  │  PythonOperator
  │                  │  AUC on holdout test set
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────────┐
  │  quality_gate        │  ShortCircuitOperator
  │  (auc >= threshold?) │  skips promote + notify if AUC too low
  └──────┬───────────────┘
         │
         ▼
  ┌──────────────┐
  │ promote_model│  PythonOperator
  │              │  MLflow: Staging → Production
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  notify_team │  EmailOperator
  │              │  Subject: "Model promoted: AUC={auc}"
  └──────────────┘
```

---

## MLflow Model Registry State Machine

```
New run registered
       │
       ▼
  ┌──────────┐
  │  None    │  (run artifact only, not registered)
  └────┬─────┘
       │  mlflow.register_model()
       ▼
  ┌──────────┐
  │  Staging │  ← train_model task lands here
  └────┬─────┘
       │  client.transition_model_version_stage("Production")
       │  only if quality_gate passes
       ▼
  ┌──────────┐
  │Production│  ← promote_model task transitions here
  └────┬─────┘
       │  (previous Production version)
       ▼
  ┌──────────┐
  │ Archived │  ← auto-archived when new version takes Production
  └──────────┘
```

---

## Data Flow: Feature Store to Model Registry

```
feature_store.parquet  (or generated synthetic data in local dev)
         │
         │  pandas.read_parquet() or generate_synthetic_data()
         ▼
train_test_split(X, y, test_size=0.2, random_state=42)
         │
         ├── X_train, y_train ──────────────────────────────────────┐
         │                                                           │
         │                                               RandomForestClassifier.fit()
         │                                                           │
         │                                               mlflow.sklearn.autolog()
         │                                               logs: n_estimators, max_depth,
         │                                                     feature_importances,
         │                                                     accuracy, f1, AUC
         │                                                           │
         └── X_test, y_test ─────────────────────────────▶ roc_auc_score(y_test, y_prob)
                                                                     │
                                                           XCom.push("run_id")
                                                           XCom.push("auc")
                                                                     │
                                                                     ▼
                                                         Airflow Variable("min_auc_threshold")
                                                         default: 0.80
                                                                     │
                                                         quality_gate: auc >= threshold?
                                                                     │
                                                           ┌─────────┴───────────┐
                                                           │                     │
                                                        promote             skip (SKIPPED)
                                                           │
                                                   mlflow.MlflowClient
                                                   .transition_model_version_stage(
                                                       name="churn_model",
                                                       version=run_id,
                                                       stage="Production"
                                                   )
```

---

## Airflow Variables Used

| Variable Key | Default | Purpose |
|---|---|---|
| `min_auc_threshold` | `0.80` | Minimum AUC to promote model to Production |
| `drift_threshold` | `0.05` | AUC drop > 5% triggers retraining |
| `model_name` | `churn_model` | MLflow model registry name |
| `notify_email` | `team@company.com` | Recipient for promotion emails |

Set these via Airflow UI: **Admin → Variables** or with the CLI:
```bash
airflow variables set min_auc_threshold 0.80
airflow variables set drift_threshold 0.05
```

---

## 📂 Navigation

⬅️ **Prev:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [09 — Data Warehouse ETL](../09_Data_Warehouse_ETL/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
