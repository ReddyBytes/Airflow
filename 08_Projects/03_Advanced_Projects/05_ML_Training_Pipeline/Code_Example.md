# ML Training Pipeline — Full DAG Code

Complete Airflow 3 DAG with KubernetesPodOperator for every ML step, accuracy-based
branching, MLflow model registration, and Asset outlet for downstream consumers.

---

```python
"""
ml_training_pipeline.py
=======================
End-to-end ML training pipeline using Airflow 3 + KubernetesPodOperator.

Steps:
  1. Validate training data (Great Expectations)
  2. Preprocess features  (KPO — CPU container)
  3. Train model          (KPO — GPU container)
  4. Evaluate accuracy    (branch on R² threshold)
  5a. Register model in MLflow   (pass branch)
  5b. Quarantine model artifact  (fail branch)
  6. Notify team                 (converge)

Required infrastructure:
  - Kubernetes cluster with GPU node pool
  - S3 bucket: ml-pipeline-bucket
  - MLflow tracking server: http://mlflow-server:5000
  - Container registry with preprocess and training images

Required Airflow connections:
  - kubernetes_default  : cluster connection
  - aws_default         : S3 access (or IRSA)

Required K8s secrets:
  - aws-credentials     : AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
  - mlflow-credentials  : MLFLOW_TRACKING_USERNAME, MLFLOW_TRACKING_PASSWORD
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import DAG, Asset
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator
from kubernetes.client import models as k8s

# ── Config ────────────────────────────────────────────────────────────────────
REGISTRY = "my-registry"
PREPROCESS_IMAGE = f"{REGISTRY}/ml-preprocess:1.0"
TRAINING_IMAGE = f"{REGISTRY}/ml-training:cuda12.1-v1.0"
NAMESPACE = "ml-workloads"
GX_ROOT = "/opt/airflow/great_expectations"
S3_BUCKET = "ml-pipeline-bucket"
MLFLOW_URI = "http://mlflow-server:5000"
MLFLOW_EXPERIMENT = "order-value-prediction"
R2_THRESHOLD = 0.85

# Asset produced by a successful model registration
MODEL_ASSET = Asset("mlflow://models/order-value-prediction/latest")


# ── Helper callables ──────────────────────────────────────────────────────────

def branch_on_model_accuracy(**context) -> str:
    """Route on R² score vs threshold."""
    metrics = context["ti"].xcom_pull(task_ids="train_model") or {}
    r2 = metrics.get("r2_score", 0.0)
    val_loss = metrics.get("val_loss", 999.0)
    mlflow_run_id = metrics.get("mlflow_run_id", "")

    print(f"[evaluate] R²={r2:.4f}, val_loss={val_loss:.4f}, "
          f"mlflow_run_id={mlflow_run_id}, threshold={R2_THRESHOLD}")

    context["ti"].xcom_push(key="r2_score", value=r2)
    context["ti"].xcom_push(key="mlflow_run_id", value=mlflow_run_id)

    return "register_model" if r2 >= R2_THRESHOLD else "quarantine_model"


def register_model_in_mlflow(**context) -> None:
    """Promote MLflow run to the Model Registry as 'Staging'."""
    import mlflow
    mlflow.set_tracking_uri(MLFLOW_URI)

    run_id = context["ti"].xcom_pull(task_ids="evaluate_metrics", key="mlflow_run_id")
    r2 = context["ti"].xcom_pull(task_ids="evaluate_metrics", key="r2_score")
    ds = context["ds"]

    client = mlflow.tracking.MlflowClient()

    # Register model (creates or increments version)
    mv = mlflow.register_model(
        model_uri=f"runs:/{run_id}/model",
        name=MLFLOW_EXPERIMENT,
    )

    # Add tags and description
    client.update_model_version(
        name=MLFLOW_EXPERIMENT,
        version=mv.version,
        description=f"Trained on {ds}. R²={r2:.4f}",
    )
    client.set_model_version_tag(
        name=MLFLOW_EXPERIMENT, version=mv.version, key="training_date", value=ds
    )
    client.set_model_version_tag(
        name=MLFLOW_EXPERIMENT, version=mv.version, key="r2_score", value=str(r2)
    )
    client.transition_model_version_stage(
        name=MLFLOW_EXPERIMENT, version=mv.version, stage="Staging"
    )

    print(f"[register] Model v{mv.version} registered as Staging. R²={r2:.4f}")


def quarantine_model_artifact(**context) -> None:
    """Tag the MLflow run as below-threshold and copy artefacts to quarantine path."""
    import mlflow
    mlflow.set_tracking_uri(MLFLOW_URI)

    run_id = context["ti"].xcom_pull(task_ids="evaluate_metrics", key="mlflow_run_id")
    r2 = context["ti"].xcom_pull(task_ids="evaluate_metrics", key="r2_score")
    ds = context["ds"]

    client = mlflow.tracking.MlflowClient()
    client.set_tag(run_id, "status", "quarantined")
    client.set_tag(run_id, "quarantine_reason", f"R²={r2:.4f} below threshold {R2_THRESHOLD}")
    client.set_tag(run_id, "training_date", ds)

    print(f"[quarantine] Run {run_id} tagged as quarantined. R²={r2:.4f} < {R2_THRESHOLD}")


def notify_team(**context) -> None:
    """Log pipeline outcome. Replace with Slack/Email in production."""
    r2 = context["ti"].xcom_pull(task_ids="evaluate_metrics", key="r2_score") or "N/A"
    run_id = context["ti"].xcom_pull(task_ids="evaluate_metrics", key="mlflow_run_id") or "N/A"
    ds = context["ds"]

    outcome = "REGISTERED" if float(r2 or 0) >= R2_THRESHOLD else "QUARANTINED"
    print(
        f"[notify] ML pipeline complete for {ds}. "
        f"Outcome: {outcome}, R²={r2}, MLflow run: {run_id}"
    )


# ── Common K8s building blocks ────────────────────────────────────────────────

aws_secret_env = k8s.V1EnvFromSource(
    secret_ref=k8s.V1SecretEnvSource(name="aws-credentials")
)
mlflow_secret_env = k8s.V1EnvFromSource(
    secret_ref=k8s.V1SecretEnvSource(name="mlflow-credentials")
)
registry_pull_secret = k8s.V1LocalObjectReference(name="registry-credentials")


# ── DAG ───────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="ml_training_pipeline",
    description="Airflow 3 ML training pipeline: ingest → validate → preprocess → train → evaluate → register",
    start_date=datetime(2024, 1, 1),
    schedule="@weekly",
    catchup=False,
    default_args={
        "owner": "ml-platform",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
        "email_on_failure": True,
        "email": "ml-team@company.com",
    },
    tags=["advanced", "ml", "kubernetes", "mlflow"],
) as dag:

    # ── Task 1: Validate training data ────────────────────────────────────────
    validate_training_data = GreatExpectationsOperator(
        task_id="validate_training_data",
        checkpoint_name="training_data_checkpoint",
        data_context_root_dir=GX_ROOT,
        checkpoint_kwargs={
            "batch_request": {
                "datasource_name": "s3_parquet_source",
                "data_connector_name": "runtime",
                "data_asset_name": f"training/{'{ds}'}",
            }
        },
        fail_task_on_validation_failure=True,
        doc_md="Validate training data quality before spending GPU compute.",
    )

    # ── Task 2: Feature preprocessing (CPU) ───────────────────────────────────
    preprocess = KubernetesPodOperator(
        task_id="preprocess_features",
        name="preprocess-{{ ds_nodash }}-{{ task_instance.try_number }}",
        namespace=NAMESPACE,
        image=PREPROCESS_IMAGE,
        image_pull_policy="Always",
        image_pull_secrets=[registry_pull_secret],
        cmds=["python", "preprocess.py"],
        env_vars={
            "PROCESSING_DATE": "{{ ds }}",
            "S3_BUCKET":        S3_BUCKET,
            "INPUT_PREFIX":     "data/training/",
            "OUTPUT_PREFIX":    "data/features/",
        },
        env_from=[aws_secret_env],
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "2", "memory": "8Gi"},
            limits={"cpu": "4",  "memory": "16Gi"},
        ),
        node_selector={"workload-type": "batch"},
        do_xcom_push=True,
        is_delete_operator_pod=True,
        get_logs=True,
        log_events_on_failure=True,
        deferrable=True,
        execution_timeout=timedelta(hours=1),
        doc_md="Scale, encode, and engineer features. Output written to S3.",
    )

    # ── Task 3: Model training (GPU) ──────────────────────────────────────────
    train = KubernetesPodOperator(
        task_id="train_model",
        name="training-{{ ds_nodash }}-{{ task_instance.try_number }}",
        namespace=NAMESPACE,
        image=TRAINING_IMAGE,
        image_pull_policy="Always",
        image_pull_secrets=[registry_pull_secret],
        cmds=["python", "train.py"],
        env_vars={
            "PROCESSING_DATE":    "{{ ds }}",
            "AIRFLOW_RUN_ID":     "{{ run_id }}",
            "S3_BUCKET":          S3_BUCKET,
            "MLFLOW_TRACKING_URI": MLFLOW_URI,
            "MLFLOW_EXPERIMENT":  MLFLOW_EXPERIMENT,
            # Feature path passed from preprocess task via Jinja + XCom
            "FEATURE_PATH": (
                "{{ task_instance.xcom_pull('preprocess_features')['feature_path'] }}"
            ),
        },
        env_from=[aws_secret_env, mlflow_secret_env],
        container_resources=k8s.V1ResourceRequirements(
            requests={"nvidia.com/gpu": "1", "cpu": "4",  "memory": "16Gi"},
            limits={"nvidia.com/gpu": "1",  "cpu": "8",  "memory": "32Gi"},
        ),
        node_selector={"accelerator": "nvidia-tesla-t4"},
        tolerations=[
            k8s.V1Toleration(
                key="nvidia.com/gpu", operator="Exists", effect="NoSchedule"
            )
        ],
        do_xcom_push=True,
        is_delete_operator_pod=True,
        get_logs=True,
        log_events_on_failure=True,
        deferrable=True,
        execution_timeout=timedelta(hours=8),
        doc_md="Train PyTorch model on GPU. Logs metrics to MLflow. Pushes R² via XCom.",
    )

    # ── Task 4: Branch on accuracy ────────────────────────────────────────────
    branch = BranchPythonOperator(
        task_id="evaluate_metrics",
        python_callable=branch_on_model_accuracy,
        doc_md=f"Branch: register if R² >= {R2_THRESHOLD}, else quarantine.",
    )

    # ── Task 5a: Register model ───────────────────────────────────────────────
    register = PythonOperator(
        task_id="register_model",
        python_callable=register_model_in_mlflow,
        outlets=[MODEL_ASSET],          # signals downstream consumers
        doc_md="Promote model to MLflow Model Registry as 'Staging'.",
    )

    # ── Task 5b: Quarantine model ─────────────────────────────────────────────
    quarantine = PythonOperator(
        task_id="quarantine_model",
        python_callable=quarantine_model_artifact,
        doc_md="Tag the MLflow run as quarantined. No registration occurs.",
    )

    # ── Task 6: Notify (converge) ─────────────────────────────────────────────
    notify = PythonOperator(
        task_id="notify_team",
        python_callable=notify_team,
        trigger_rule="none_failed_min_one_success",
        doc_md="Log outcome. Replace with Slack/email in production.",
    )

    # ── Dependencies ──────────────────────────────────────────────────────────
    validate_training_data >> preprocess >> train >> branch
    branch >> register   >> notify
    branch >> quarantine >> notify
```

---

## Testing Locally (Without GPU)

```bash
# Override image to a CPU-only mock trainer
airflow dags trigger ml_training_pipeline \
  --conf '{"training_image": "my-registry/ml-training-cpu-mock:1.0"}' \
  --exec-date 2024-01-15
```

Create a CPU mock training image that produces realistic XCom output but skips
actual PyTorch training:
```python
# mock_train.py
import json, os
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({
        "r2_score": 0.91,
        "val_loss": 0.042,
        "mlflow_run_id": "mock-run-id-001",
        "model_path": "s3://ml-pipeline-bucket/models/mock/",
    }, f)
print("Mock training complete. R²=0.91")
```

---

## 📂 Navigation

| | |
|---|---|
| **Project Guide** | [Project_Guide.md](./Project_Guide.md) |
| **Step-by-Step** | [Step_by_Step.md](./Step_by_Step.md) |
| **Parent: Advanced Projects** | [03_Advanced_Projects](../Readme.md) |
| **Next: Event-Driven Asset Pipeline** | [06_Event_Driven_Asset_Pipeline](../06_Event_Driven_Asset_Pipeline/Project_Guide.md) |
