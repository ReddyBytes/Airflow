"""
ml_training_pipeline_starter.py
================================
Scaffold for the ML Training Pipeline capstone.

Your job: fill in the TODO sections below.
The DAG structure, task IDs, and dependency wiring are given.
You implement the callable logic and KPO parameters.

Difficulty: Minimal Hints (structure given, parameters and logic are yours)
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import DAG, Asset
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

# ── Config ────────────────────────────────────────────────────────────────────
REGISTRY           = "my-registry"
PREPROCESS_IMAGE   = f"{REGISTRY}/ml-preprocess:1.0"
TRAINING_IMAGE     = f"{REGISTRY}/ml-training:cuda12.1-v1.0"
NAMESPACE          = "ml-workloads"
S3_BUCKET          = "ml-pipeline-bucket"
MLFLOW_URI         = "http://mlflow-server:5000"
MLFLOW_EXPERIMENT  = "order-value-prediction"
R2_THRESHOLD       = 0.85   # R² below this → quarantine

# Asset emitted when a model passes evaluation and is registered
MODEL_ASSET = Asset("mlflow://models/order-value-prediction/latest")


# ── Callable: branch on accuracy ──────────────────────────────────────────────

def branch_on_model_accuracy(**context) -> str:
    """
    Read R² score from train_model XCom.
    Return "register_model" if r2 >= R2_THRESHOLD, else "quarantine_model".

    TODO:
      - Pull XCom from task_ids="train_model"
      - Extract r2_score (default to 0.0 if missing)
      - Push r2_score and mlflow_run_id as separate XCom keys for downstream tasks
      - Return the correct task ID string
    """
    # TODO: implement branching logic
    raise NotImplementedError("Implement branch_on_model_accuracy")


# ── Callable: register model ──────────────────────────────────────────────────

def register_model_in_mlflow(**context) -> None:
    """
    Promote the MLflow run to the Model Registry as "Staging".

    TODO:
      - Pull mlflow_run_id and r2_score from evaluate_metrics XCom
      - Use mlflow.register_model() to create/increment a model version
      - Add description and tags (training_date, r2_score)
      - Transition version to "Staging" stage
    """
    # TODO: implement model registration
    raise NotImplementedError("Implement register_model_in_mlflow")


# ── Callable: quarantine model ────────────────────────────────────────────────

def quarantine_model_artifact(**context) -> None:
    """
    Tag the MLflow run as quarantined so it is easy to find and investigate.

    TODO:
      - Pull mlflow_run_id from evaluate_metrics XCom
      - Use mlflow.tracking.MlflowClient() to set tags: status=quarantined,
        quarantine_reason, training_date
    """
    # TODO: implement quarantine logic
    raise NotImplementedError("Implement quarantine_model_artifact")


# ── Callable: notify ──────────────────────────────────────────────────────────

def notify_team(**context) -> None:
    """
    Log the pipeline outcome. Replace print() with Slack/email in production.

    TODO:
      - Pull r2_score and mlflow_run_id from evaluate_metrics XCom
      - Print outcome: REGISTERED or QUARANTINED, score, run ID, date
    """
    # TODO: implement notification
    raise NotImplementedError("Implement notify_team")


# ── Common K8s building blocks ────────────────────────────────────────────────

# TODO: define aws_secret_env and mlflow_secret_env using k8s.V1EnvFromSource
# Hint: k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name="aws-credentials"))
aws_secret_env    = None  # TODO
mlflow_secret_env = None  # TODO


# ── DAG ───────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="ml_training_pipeline",
    description="Airflow 3 ML training: validate → preprocess → train → evaluate → register/quarantine",
    start_date=datetime(2024, 1, 1),
    schedule="@weekly",
    catchup=False,
    default_args={
        "owner": "ml-platform",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["capstone", "ml", "kubernetes"],
) as dag:

    # Task 1: Validate training data
    # TODO: replace EmptyOperator with GreatExpectationsOperator or a PythonOperator
    # that checks the S3 training file exists and has a minimum row count
    validate_training_data = EmptyOperator(task_id="validate_training_data")

    # Task 2: Preprocess features (CPU container)
    # TODO: configure KubernetesPodOperator with:
    #   - PREPROCESS_IMAGE, NAMESPACE
    #   - env_vars: PROCESSING_DATE="{{ ds }}", S3_BUCKET
    #   - container_resources: 2 CPU / 8Gi requests, 4 CPU / 16Gi limits
    #   - do_xcom_push=True, is_delete_operator_pod=True, get_logs=True, deferrable=True
    preprocess = EmptyOperator(task_id="preprocess_features")  # TODO: replace with KPO

    # Task 3: Train model (GPU container)
    # TODO: configure KubernetesPodOperator with:
    #   - TRAINING_IMAGE, NAMESPACE
    #   - env_vars: PROCESSING_DATE, AIRFLOW_RUN_ID, FEATURE_PATH (from preprocess XCom via Jinja),
    #               MLFLOW_TRACKING_URI, MLFLOW_EXPERIMENT
    #   - GPU resource requests/limits (nvidia.com/gpu: "1")
    #   - node_selector: accelerator: nvidia-tesla-t4
    #   - V1Toleration for nvidia.com/gpu
    #   - do_xcom_push=True, deferrable=True, execution_timeout=timedelta(hours=8)
    train = EmptyOperator(task_id="train_model")  # TODO: replace with KPO

    # Task 4: Branch on accuracy
    branch = BranchPythonOperator(
        task_id="evaluate_metrics",
        python_callable=branch_on_model_accuracy,
    )

    # Task 5a: Register model (outlets=[MODEL_ASSET] so serving DAG triggers)
    register = PythonOperator(
        task_id="register_model",
        python_callable=register_model_in_mlflow,
        outlets=[MODEL_ASSET],
    )

    # Task 5b: Quarantine model
    quarantine = PythonOperator(
        task_id="quarantine_model",
        python_callable=quarantine_model_artifact,
    )

    # Task 6: Notify (converge both branches)
    # TODO: set trigger_rule="none_failed_min_one_success"
    notify = PythonOperator(
        task_id="notify_team",
        python_callable=notify_team,
        # trigger_rule=...  TODO
    )

    # ── Dependencies ──────────────────────────────────────────────────────────
    validate_training_data >> preprocess >> train >> branch
    branch >> register   >> notify
    branch >> quarantine >> notify
