"""
Project 08 — ML Model Retraining Pipeline
DAG Starter: All 7 tasks instantiated as stubs. Fill in the logic.
"""

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator, ShortCircuitOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.email import EmailOperator
from airflow.models import Variable
from datetime import datetime, timedelta

# TODO: Import mlflow, mlflow.sklearn, MlflowClient
# TODO: Import sklearn: RandomForestClassifier, train_test_split, roc_auc_score
# TODO: Import numpy and pandas

default_args = {
    "owner": "ml-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


# ─── Helper: load or generate training data ───────────────────────────────────

def load_training_data():
    """
    TODO: Either read from a real feature store (parquet/S3) or
    generate synthetic binary classification data using sklearn.datasets.make_classification().
    Returns: X_train, X_test, y_train, y_test
    """
    # TODO: implement
    pass


# ─── Task 1: Check drift ──────────────────────────────────────────────────────

def check_drift(**context) -> dict:
    """
    TODO:
    1. Connect to MLflow (http://mlflow:5000)
    2. Get the latest Production model version
    3. Retrieve its AUC metric history
    4. Compare current AUC to rolling 7-day mean
    5. Push {"needs_retrain": bool, "current_auc": float, "baseline_auc": float} to XCom
    6. If no Production model exists, return needs_retrain=True
    """
    # TODO: implement
    pass


# ─── Task 2: Branching logic ──────────────────────────────────────────────────

def drift_gate(**context) -> str:
    """
    TODO:
    1. Pull drift result from XCom (task_ids='check_drift')
    2. Return 'retrain_start' if needs_retrain is True
    3. Return 'skip_retrain' otherwise
    """
    # TODO: implement
    pass


# ─── Task 3: Train model ──────────────────────────────────────────────────────

def train_model(**context) -> None:
    """
    TODO:
    1. Load training data (use load_training_data())
    2. Set MLflow tracking URI and experiment name
    3. Start a run, call mlflow.sklearn.autolog() BEFORE fit
    4. Fit RandomForestClassifier(n_estimators=100, max_depth=10)
    5. Register model in MLflow Model Registry (Staging stage)
    6. Push run_id and model_version to XCom
    """
    # TODO: implement
    pass


# ─── Task 4: Evaluate model ───────────────────────────────────────────────────

def evaluate_model(**context) -> None:
    """
    TODO:
    1. Pull run_id from XCom (task_ids='train_model', key='run_id')
    2. Load test data
    3. Load model from MLflow: mlflow.sklearn.load_model(f"runs:/{run_id}/model")
    4. Compute AUC: roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    5. Log AUC to MLflow run
    6. Push auc to XCom with key='auc'
    """
    # TODO: implement
    pass


# ─── Task 5: Quality gate ─────────────────────────────────────────────────────

def auc_passes_threshold(**context) -> bool:
    """
    TODO:
    1. Pull AUC from XCom (task_ids='evaluate_model', key='auc')
    2. Get threshold from Variable.get('min_auc_threshold', default_var='0.80')
    3. Return True if auc >= threshold, False otherwise
    4. Log both values
    """
    # TODO: implement
    pass


# ─── Task 6: Promote model ────────────────────────────────────────────────────

def promote_model(**context) -> None:
    """
    TODO:
    1. Pull model_version from XCom (task_ids='train_model', key='model_version')
    2. Create MlflowClient
    3. Transition model version to 'Production' stage
    4. Set archive_existing_versions=True
    5. Log confirmation message
    """
    # TODO: implement
    pass


# ─── DAG definition ───────────────────────────────────────────────────────────

with DAG(
    dag_id="ml_model_retraining_pipeline",
    default_args=default_args,
    schedule_interval="0 6 * * *",      # daily at 6am
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ml", "mlflow", "retraining"],
) as dag:

    check_drift_task = PythonOperator(
        task_id="check_drift",
        python_callable=check_drift,
    )

    # TODO: Replace with BranchPythonOperator
    drift_gate_task = PythonOperator(
        task_id="drift_gate_branch",
        python_callable=drift_gate,         # change to BranchPythonOperator
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

    # TODO: Replace with ShortCircuitOperator
    quality_gate = PythonOperator(
        task_id="quality_gate",
        python_callable=auc_passes_threshold,  # change to ShortCircuitOperator
    )

    promote_task = PythonOperator(
        task_id="promote_model",
        python_callable=promote_model,
    )

    # TODO: Replace with EmailOperator using Jinja for subject/body
    notify_task = PythonOperator(
        task_id="notify_team",
        python_callable=lambda **ctx: print("[STUB] Send email here"),
    )

    # TODO: Wire up dependencies
    # check_drift_task >> drift_gate_task >> [retrain_start, skip_retrain]
    # retrain_start >> train_task >> evaluate_task >> quality_gate >> promote_task >> notify_task
