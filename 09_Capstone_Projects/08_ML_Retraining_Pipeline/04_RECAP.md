# Project 08 — Recap

---

## What You Built

A seven-task conditional DAG that closes the MLOps feedback loop. The pipeline detects when a production model has drifted, retrains it with MLflow tracking, applies a quality gate, and promotes the model only when it meets the AUC threshold.

```
check_drift → drift_gate_branch → [retrain_start → train_model → evaluate_model
                                   → quality_gate → promote_model → notify_team]
                                 OR [skip_retrain]
```

---

## Key Concepts

### The MLOps Loop

MLOps is to models what CI/CD is to software. The loop is:

```
Monitor → Detect drift → Retrain → Evaluate → Gate → Promote → Monitor
```

Without automation, data scientists retrain models manually, inconsistently, and too infrequently. This DAG replaces that manual process with a repeatable, auditable pipeline.

### BranchPythonOperator Patterns

`BranchPythonOperator` routes DAG execution by returning a `task_id` string (or a list of strings). All tasks not in the returned list are automatically `SKIPPED`. Key rules:

- Tasks immediately downstream of a branch must be direct children in the `>>` chain
- Tasks farther downstream (grandchildren) will also be skipped by default
- Use `trigger_rule="none_failed_min_one_success"` on tasks that should run regardless of which branch was taken (e.g., a final cleanup step)

### ShortCircuitOperator: The Quality Gate

`ShortCircuitOperator` is a `PythonOperator` that short-circuits (skips all downstream tasks) when it returns `False`. It is the correct pattern for "optional steps that only run when a condition is met" — as opposed to raising an exception (which marks downstream tasks `UPSTREAM_FAILED`).

Set `ignore_downstream_trigger_rules=True` to ensure that tasks with `trigger_rule="all_done"` farther downstream are also skipped, not just direct children.

### MLflow + Airflow Integration

| Concern | Airflow | MLflow |
|---|---|---|
| Scheduling | ✅ | |
| Parameter logging | | ✅ autolog |
| Metric tracking | | ✅ |
| Model versioning | | ✅ registry |
| Conditional logic | ✅ BranchPythonOperator | |
| Quality gates | ✅ ShortCircuitOperator | |
| Notifications | ✅ EmailOperator | |

The two tools are complementary. Airflow owns the orchestration; MLflow owns the experiment tracking and model lifecycle.

### Airflow Variables for Thresholds

Hardcoding thresholds in DAG code is a maintenance problem — every change requires a deploy. Variables let you adjust thresholds from the Airflow UI without touching code. The pattern:

```python
threshold = float(Variable.get("min_auc_threshold", default_var="0.80"))
```

The `default_var` ensures the DAG works even if the Variable hasn't been set yet.

---

## Extend It

**Add Feast feature store**
Replace the synthetic data with a real feature store. Feast provides a `FeatureStore.get_historical_features()` API that returns a pandas DataFrame. The Airflow task calls Feast with a `retrieval_job` that filters by `event_timestamp < logical_date`. This makes the pipeline temporally correct — no future data leaks into training.

**Use Ray Train for distributed training**
When the dataset is too large for a single node, replace `clf.fit()` with Ray Train's `TorchTrainer` or `SklearnTrainer`. The Airflow task submits the Ray job via `RayJobOperator` (from `apache-airflow-providers-ray`) and polls for completion.

**Add Evidently for drift reports**
Instead of comparing AUC scores manually, use Evidently AI to generate a full data drift report comparing the production dataset (reference) to the current batch (current). Evidently produces an HTML report and a JSON summary. Log the JSON summary to MLflow and use it in the `check_drift` task for richer drift detection (not just AUC — also feature distributions, PSI, KL divergence).

**Add model explainability**
After training, compute SHAP values for the test set and log the summary plot as a MLflow artifact. The `notify_team` email can include a link to the SHAP plot so the data science team can verify the model is using the right features after retraining.

---

## 📂 Navigation

⬅️ **Prev:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [09 — Data Warehouse ETL](../09_Data_Warehouse_ETL/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
