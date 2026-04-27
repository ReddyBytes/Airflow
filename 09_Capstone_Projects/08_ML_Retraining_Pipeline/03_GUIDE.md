# Project 08 — Step-by-Step Guide

> Difficulty: 🟡 Partially Guided. Each step gives you the concept and signature. You write the logic.
> Open `src/solution.py` only after a genuine attempt.

---

## Setup: Docker Compose (add MLflow)

Before writing the DAG, spin up MLflow alongside Airflow:

```yaml
# Add to your docker-compose.yml:
  mlflow:
    image: ghcr.io/mlflow/mlflow:v2.10.0
    command: mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:///mlflow.db
    ports:
      - "5000:5000"
    volumes:
      - mlflow_data:/mlflow
```

Set Airflow Variables (via UI or CLI):
```bash
airflow variables set min_auc_threshold 0.80
airflow variables set drift_threshold 0.05
airflow variables set model_name churn_model
airflow variables set notify_email team@company.com
```

---

## Step 1 — Write `check_drift`

**Concept:** This task compares the current production model's AUC to the rolling 7-day mean AUC logged in MLflow. If the drop exceeds the `drift_threshold` Variable, we need to retrain.

**Signature:**
```python
def check_drift(**context) -> dict:
    """
    Returns: {"needs_retrain": bool, "current_auc": float, "baseline_auc": float}
    Pushes result to XCom.
    """
```

**Hints:**
- Use `mlflow.MlflowClient().get_latest_versions(name, stages=["Production"])` to get the current model version
- Use `client.get_metric_history(run_id, "auc")` to get the AUC history
- If no Production model exists, always return `needs_retrain=True`
- Compare: `baseline_auc - current_auc > float(Variable.get("drift_threshold"))`

---

## Step 2 — Write `drift_gate_branch`

**Concept:** `BranchPythonOperator` returns the `task_id` of the next task to run. All other branches are automatically marked `SKIPPED`. This is how Airflow implements conditional logic without `if/else` in a linear DAG.

**Signature:**
```python
def drift_gate(**context) -> str:
    """Returns 'retrain_start' or 'skip_retrain'."""
```

**Hints:**
- Pull the drift result from XCom: `context["ti"].xcom_pull(task_ids="check_drift")`
- Return the task_id string, not a boolean
- The `BranchPythonOperator` does the routing — your function just decides which string to return

**Common mistake:** Forgetting to set `trigger_rule="none_failed_min_one_success"` on tasks downstream of a branch. Without it, skipped branches cause downstream tasks to be skipped too.

---

## Step 3 — Write `train_model`

**Concept:** `mlflow.sklearn.autolog()` automatically captures model parameters, metrics, feature importances, and the serialized model artifact — you get all of this for free by calling it before `.fit()`. The only thing you need to do manually is register the model in the registry.

**Signature:**
```python
def train_model(**context) -> None:
    """
    Trains RandomForestClassifier.
    Logs run to MLflow. Registers model in Staging.
    Pushes run_id and model_version to XCom.
    """
```

**Hints:**
```python
import mlflow
import mlflow.sklearn

mlflow.set_tracking_uri("http://mlflow:5000")
mlflow.set_experiment("churn_retraining")

with mlflow.start_run() as run:
    mlflow.sklearn.autolog()                        # ← must call BEFORE .fit()
    clf = RandomForestClassifier(n_estimators=100)
    clf.fit(X_train, y_train)
    # After the with block closes, autolog captures everything automatically

    # Register the model:
    model_uri = f"runs:/{run.info.run_id}/model"
    result = mlflow.register_model(model_uri, Variable.get("model_name"))
    # result.version is the new version number
```

---

## Step 4 — Write `evaluate_model`

**Concept:** After training, we evaluate on the holdout test set. The AUC is the decision metric. Log it to the same MLflow run, then push it to XCom so the `quality_gate` can read it.

**Signature:**
```python
def evaluate_model(**context) -> None:
    """
    Loads the just-trained model from MLflow.
    Computes AUC on test set. Logs metric. Pushes auc to XCom.
    """
```

**Hints:**
- Pull `run_id` from XCom to load the correct model version
- `mlflow.sklearn.load_model(f"runs:/{run_id}/model")` retrieves the artifact
- `roc_auc_score(y_test, clf.predict_proba(X_test)[:, 1])` for binary AUC
- Use `mlflow.log_metric("test_auc", auc)` to log it to the same run

---

## Step 5 — Write the `quality_gate` ShortCircuitOperator

**Concept:** `ShortCircuitOperator` calls your function. If it returns `False`, all downstream tasks are marked `SKIPPED` and the DAG run ends cleanly (not as a failure). This is the correct Airflow pattern for "optional steps that only run when quality is met."

**Signature:**
```python
def auc_passes_threshold(**context) -> bool:
    """Returns True if AUC >= Airflow Variable 'min_auc_threshold'."""
```

**Hints:**
- Pull AUC from XCom: `context["ti"].xcom_pull(task_ids="evaluate_model", key="auc")`
- Compare against `float(Variable.get("min_auc_threshold", default_var="0.80"))`
- Log the comparison result so it's visible in task logs
- Set `ignore_downstream_trigger_rules=True` on the `ShortCircuitOperator` to ensure all descendants are skipped (not just direct children)

---

## Step 6 — Write `promote_model`

**Concept:** Promotion means transitioning the model from `Staging` to `Production` in the MLflow Model Registry. MLflow automatically archives the previous Production version.

**Signature:**
```python
def promote_model(**context) -> None:
    """Transitions the trained model version to Production stage in MLflow."""
```

**Hints:**
```python
client = mlflow.MlflowClient(tracking_uri="http://mlflow:5000")
model_version = context["ti"].xcom_pull(task_ids="train_model", key="model_version")
client.transition_model_version_stage(
    name=Variable.get("model_name"),
    version=model_version,
    stage="Production",
    archive_existing_versions=True,     # ← archives old Production automatically
)
```

---

## Step 7 — Write the Email Notification

**Concept:** `EmailOperator` sends an email at the end of the successful path. The subject and body can use Jinja templates to include run metadata.

```python
from airflow.operators.email import EmailOperator

notify_team = EmailOperator(
    task_id="notify_team",
    to=Variable.get("notify_email"),
    subject="[Airflow] Churn model promoted — AUC: {{ ti.xcom_pull(task_ids='evaluate_model', key='auc') | round(4) }}",
    html_content="""
        <h3>Model Promotion Complete</h3>
        <p>A new version of <b>{{ var.value.model_name }}</b> has been promoted to Production.</p>
        <ul>
            <li>Run ID: {{ ti.xcom_pull(task_ids='train_model', key='run_id') }}</li>
            <li>Test AUC: {{ ti.xcom_pull(task_ids='evaluate_model', key='auc') | round(4) }}</li>
            <li>Threshold: {{ var.value.min_auc_threshold }}</li>
        </ul>
        <p>View in <a href="http://mlflow:5000">MLflow UI</a></p>
    """,
)
```

**SMTP config** (in `airflow.cfg` or environment variables):
```
AIRFLOW__SMTP__SMTP_HOST=smtp.gmail.com
AIRFLOW__SMTP__SMTP_PORT=587
AIRFLOW__SMTP__SMTP_USER=your@email.com
AIRFLOW__SMTP__SMTP_PASSWORD=app_password
AIRFLOW__SMTP__SMTP_MAIL_FROM=your@email.com
```

---

## Testing the Branch Logic

To test the "no drift" path without waiting for drift:
```python
# Temporarily override drift_threshold to a very high value
airflow variables set drift_threshold 999.0
airflow dags trigger ml_model_retraining_pipeline
# Should see: check_drift → drift_gate_branch → skip_retrain → [4 tasks SKIPPED]

# Test the retrain path:
airflow variables set drift_threshold 0.0
airflow dags trigger ml_model_retraining_pipeline
# Should see: all 7 tasks run
```

---

## 📂 Navigation

⬅️ **Prev:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [09 — Data Warehouse ETL](../09_Data_Warehouse_ETL/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
