"""
Project 08 — ML Model Retraining Pipeline
Complete Solution DAG
"""

import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn

from datetime import datetime, timedelta
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator, ShortCircuitOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.email import EmailOperator
from airflow.models import Variable

MLFLOW_URI   = "http://mlflow:5000"
EXPERIMENT   = "churn_retraining"
MODEL_NAME   = "churn_model"            # overridden by Variable at runtime

default_args = {
    "owner": "ml-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


# ─── Helper ───────────────────────────────────────────────────────────────────

def load_training_data():
    """
    Generates synthetic binary classification data.
    In production: replace with pd.read_parquet("s3://feature-store/churn/...")
    """
    X, y = make_classification(
        n_samples=5000,
        n_features=20,
        n_informative=10,
        n_redundant=5,
        random_state=42,
    )
    return train_test_split(X, y, test_size=0.2, random_state=42)


# ─── Task 1: Check drift ──────────────────────────────────────────────────────

def check_drift(**context) -> None:
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = mlflow.MlflowClient()

    model_name = Variable.get("model_name", default_var=MODEL_NAME)
    drift_threshold = float(Variable.get("drift_threshold", default_var="0.05"))

    try:
        versions = client.get_latest_versions(model_name, stages=["Production"])
    except Exception:
        versions = []

    if not versions:
        # No production model — always retrain
        result = {"needs_retrain": True, "current_auc": 0.0, "baseline_auc": 0.0}
        context["ti"].xcom_push(key="drift_result", value=result)
        print("[INFO] No Production model found — retraining required")
        return

    run_id = versions[0].run_id

    try:
        history = client.get_metric_history(run_id, "test_auc")
        current_auc = history[-1].value if history else 0.0
    except Exception:
        current_auc = 0.0

    # Rolling 7-day baseline: fetch recent runs from the experiment
    try:
        experiment = client.get_experiment_by_name(EXPERIMENT)
        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string="attributes.status = 'FINISHED'",
            order_by=["attribute.start_time DESC"],
            max_results=7,
        )
        recent_aucs = []
        for r in runs:
            if "test_auc" in r.data.metrics:
                recent_aucs.append(r.data.metrics["test_auc"])
        baseline_auc = float(np.mean(recent_aucs)) if recent_aucs else current_auc
    except Exception:
        baseline_auc = current_auc

    drift = baseline_auc - current_auc
    needs_retrain = drift > drift_threshold

    result = {
        "needs_retrain": needs_retrain,
        "current_auc":   round(current_auc, 4),
        "baseline_auc":  round(baseline_auc, 4),
        "drift":         round(drift, 4),
    }
    context["ti"].xcom_push(key="drift_result", value=result)
    print(f"[INFO] Drift check: current={current_auc:.4f} baseline={baseline_auc:.4f} "
          f"drift={drift:.4f} threshold={drift_threshold} retrain={needs_retrain}")


# ─── Task 2: Branch ───────────────────────────────────────────────────────────

def drift_gate(**context) -> str:
    result = context["ti"].xcom_pull(task_ids="check_drift", key="drift_result")
    if result and result.get("needs_retrain"):
        print("[INFO] Drift detected — routing to retrain_start")
        return "retrain_start"
    print("[INFO] No drift — routing to skip_retrain")
    return "skip_retrain"


# ─── Task 3: Train model ──────────────────────────────────────────────────────

def train_model(**context) -> None:
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(EXPERIMENT)

    X_train, X_test, y_train, y_test = load_training_data()
    model_name = Variable.get("model_name", default_var=MODEL_NAME)

    with mlflow.start_run() as run:
        mlflow.sklearn.autolog()                                # ← captures everything on fit()

        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_leaf=5,
            n_jobs=-1,
            random_state=42,
        )
        clf.fit(X_train, y_train)

        run_id = run.info.run_id

    # Register model in Staging
    model_uri = f"runs:/{run_id}/model"
    registered = mlflow.register_model(model_uri, model_name)
    model_version = registered.version

    context["ti"].xcom_push(key="run_id", value=run_id)
    context["ti"].xcom_push(key="model_version", value=model_version)
    print(f"[INFO] Trained and registered model: run={run_id} version={model_version}")


# ─── Task 4: Evaluate model ───────────────────────────────────────────────────

def evaluate_model(**context) -> None:
    mlflow.set_tracking_uri(MLFLOW_URI)

    run_id = context["ti"].xcom_pull(task_ids="train_model", key="run_id")
    _, X_test, _, y_test = load_training_data()                 # ← same seed = same test split

    model = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
    y_prob = model.predict_proba(X_test)[:, 1]
    auc = round(roc_auc_score(y_test, y_prob), 4)

    with mlflow.start_run(run_id=run_id):                       # ← log into the same run
        mlflow.log_metric("test_auc", auc)

    context["ti"].xcom_push(key="auc", value=auc)
    print(f"[INFO] Evaluated model: test_auc={auc}")


# ─── Task 5: Quality gate ─────────────────────────────────────────────────────

def auc_passes_threshold(**context) -> bool:
    auc = context["ti"].xcom_pull(task_ids="evaluate_model", key="auc")
    threshold = float(Variable.get("min_auc_threshold", default_var="0.80"))
    passes = auc >= threshold
    print(f"[INFO] Quality gate: auc={auc} threshold={threshold} passes={passes}")
    return passes                                               # ← False skips all downstream


# ─── Task 6: Promote model ────────────────────────────────────────────────────

def promote_model(**context) -> None:
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = mlflow.MlflowClient()

    model_version = context["ti"].xcom_pull(task_ids="train_model", key="model_version")
    model_name = Variable.get("model_name", default_var=MODEL_NAME)

    client.transition_model_version_stage(
        name=model_name,
        version=model_version,
        stage="Production",
        archive_existing_versions=True,     # ← previous Production → Archived automatically
    )
    print(f"[INFO] Promoted {model_name} v{model_version} to Production")


# ─── DAG definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="ml_model_retraining_pipeline",
    default_args=default_args,
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ml", "mlflow", "retraining"],
) as dag:

    check_drift_task = PythonOperator(
        task_id="check_drift",
        python_callable=check_drift,
    )

    drift_gate_task = BranchPythonOperator(
        task_id="drift_gate_branch",
        python_callable=drift_gate,
    )

    retrain_start = DummyOperator(task_id="retrain_start")
    skip_retrain  = DummyOperator(task_id="skip_retrain")

    train_task = PythonOperator(
        task_id="train_model",
        python_callable=train_model,
    )

    evaluate_task = PythonOperator(
        task_id="evaluate_model",
        python_callable=evaluate_model,
    )

    quality_gate = ShortCircuitOperator(
        task_id="quality_gate",
        python_callable=auc_passes_threshold,
        ignore_downstream_trigger_rules=True,   # ← ensures all descendants skip, not just direct
    )

    promote_task = PythonOperator(
        task_id="promote_model",
        python_callable=promote_model,
        trigger_rule="none_failed_min_one_success",
    )

    notify_task = EmailOperator(
        task_id="notify_team",
        to=Variable.get("notify_email", default_var="team@company.com"),
        subject="[Airflow] Churn model promoted — AUC: "
                "{{ ti.xcom_pull(task_ids='evaluate_model', key='auc') }}",
        html_content="""
            <h3>Model Promotion Complete</h3>
            <p>A new version of <b>churn_model</b> has been promoted to Production.</p>
            <ul>
                <li>Run ID: {{ ti.xcom_pull(task_ids='train_model', key='run_id') }}</li>
                <li>Model Version: {{ ti.xcom_pull(task_ids='train_model', key='model_version') }}</li>
                <li>Test AUC: {{ ti.xcom_pull(task_ids='evaluate_model', key='auc') }}</li>
                <li>Threshold: {{ var.value.min_auc_threshold }}</li>
            </ul>
            <p>View details in <a href="http://mlflow:5000">MLflow UI</a></p>
        """,
        trigger_rule="none_failed_min_one_success",
    )

    # Path A: drift detected
    check_drift_task >> drift_gate_task >> [retrain_start, skip_retrain]
    retrain_start >> train_task >> evaluate_task >> quality_gate >> promote_task >> notify_task
