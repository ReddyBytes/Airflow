# ML Training Pipeline — Step by Step

This project builds a production-style machine learning training pipeline using
Airflow 3 and KubernetesPodOperator. Each step runs in an isolated container,
enabling per-step GPU allocation, custom Docker images, and reproducible
environments.

---

## What You Will Build

```
ingest_training_data (S3)
        ↓
validate_data (Great Expectations)
        ↓
preprocess_features (KPO — CPU container)
        ↓
train_model (KPO — GPU container)
        ↓
evaluate_metrics
        ↓
  [branch on accuracy threshold]
   /                           \
register_model (MLflow)    quarantine_model
```

---

## Prerequisites

```bash
pip install apache-airflow \
            apache-airflow-providers-cncf-kubernetes \
            apache-airflow-providers-amazon \
            apache-airflow-providers-great-expectations \
            mlflow \
            kubernetes
```

Infrastructure needed:
- Kubernetes cluster (EKS, GKE, or local with `kind`)
- GPU node pool (for training step)
- S3 bucket for training data and model artefacts
- MLflow tracking server

---

## Step 1 — Prepare Training Data in S3

```bash
# Create S3 structure
aws s3 mb s3://ml-pipeline-bucket

# Upload training data (your actual dataset)
aws s3 cp ./data/training_2024-01-15.parquet s3://ml-pipeline-bucket/data/training/2024-01-15/
aws s3 cp ./data/validation_2024-01-15.parquet s3://ml-pipeline-bucket/data/validation/2024-01-15/
```

The pipeline uses `{{ ds }}` to locate the correct date partition automatically.

---

## Step 2 — Build the Docker Images

You need two images: one for CPU preprocessing and one GPU-enabled for training.

**Preprocessing image** (`docker/preprocess/Dockerfile`):
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements-preprocess.txt .
RUN pip install -r requirements-preprocess.txt
COPY src/preprocess.py .
CMD ["python", "preprocess.py"]
```

**Training image** (`docker/training/Dockerfile`):
```dockerfile
FROM nvcr.io/nvidia/pytorch:24.01-py3
WORKDIR /app
COPY requirements-training.txt .
RUN pip install -r requirements-training.txt
COPY src/train.py .
CMD ["python", "train.py"]
```

Build and push:
```bash
docker build -t my-registry/ml-preprocess:1.0 -f docker/preprocess/Dockerfile .
docker push my-registry/ml-preprocess:1.0

docker build -t my-registry/ml-training:1.0 -f docker/training/Dockerfile .
docker push my-registry/ml-training:1.0
```

---

## Step 3 — Write the Preprocess Script

```python
# src/preprocess.py
import sys, os, json
import pandas as pd
import boto3

date = os.environ["PROCESSING_DATE"]
input_path = f"s3://ml-pipeline-bucket/data/training/{date}/"
output_path = f"s3://ml-pipeline-bucket/data/features/{date}/"

df = pd.read_parquet(input_path)

# Feature engineering
df["feature_1_scaled"] = (df["feature_1"] - df["feature_1"].mean()) / df["feature_1"].std()
df["feature_2_log"] = df["feature_2"].clip(lower=0).apply(lambda x: x ** 0.5)
df = df.dropna()

df.to_parquet(output_path, index=False)
print(f"Preprocessed {len(df)} rows → {output_path}")

# XCom output for Airflow
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({"feature_path": output_path, "row_count": len(df)}, f)
```

---

## Step 4 — Write the Training Script

```python
# src/train.py
import sys, os, json
import torch
import mlflow
import mlflow.pytorch

date = os.environ["PROCESSING_DATE"]
run_id = os.environ.get("AIRFLOW_RUN_ID", "unknown")
feature_path = os.environ["FEATURE_PATH"]

mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
mlflow.set_experiment("order-value-prediction")

with mlflow.start_run(run_name=f"run-{date}-{run_id}") as run:
    # --- Load features ---
    import pandas as pd
    df = pd.read_parquet(feature_path)
    X = torch.tensor(df.drop("target", axis=1).values, dtype=torch.float32)
    y = torch.tensor(df["target"].values, dtype=torch.float32)

    # --- Train a simple model ---
    model = torch.nn.Sequential(
        torch.nn.Linear(X.shape[1], 64),
        torch.nn.ReLU(),
        torch.nn.Linear(64, 1),
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = torch.nn.MSELoss()

    for epoch in range(100):
        optimizer.zero_grad()
        pred = model(X).squeeze()
        loss = criterion(pred, y)
        loss.backward()
        optimizer.step()

    # --- Evaluate ---
    with torch.no_grad():
        val_df = pd.read_parquet(f"s3://ml-pipeline-bucket/data/validation/{date}/")
        Xv = torch.tensor(val_df.drop("target", axis=1).values, dtype=torch.float32)
        yv = torch.tensor(val_df["target"].values, dtype=torch.float32)
        val_pred = model(Xv).squeeze()
        val_loss = criterion(val_pred, yv).item()
        # R² score (simplified)
        ss_res = ((yv - val_pred) ** 2).sum().item()
        ss_tot = ((yv - yv.mean()) ** 2).sum().item()
        r2 = 1 - ss_res / ss_tot

    mlflow.log_metric("val_loss", val_loss)
    mlflow.log_metric("r2_score", r2)
    mlflow.pytorch.log_model(model, "model")

    model_path = f"s3://ml-pipeline-bucket/models/{date}/{run.info.run_id}/"
    print(f"R² = {r2:.4f}, val_loss = {val_loss:.4f}")
    print(f"MLflow run_id: {run.info.run_id}")

# XCom output
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({
        "r2_score": r2,
        "val_loss": val_loss,
        "mlflow_run_id": run.info.run_id,
        "model_path": model_path,
    }, f)
```

---

## Step 5 — Write the DAG

```python
# dags/ml_training_pipeline.py
from datetime import datetime, timedelta
from airflow.sdk import DAG
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

ACCURACY_THRESHOLD = 0.85          # R² below this triggers quarantine

with DAG(
    dag_id="ml_training_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@weekly",
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=10)},
    tags=["advanced", "ml", "kubernetes"],
) as dag:

    # Task 1: Validate training data with Great Expectations
    validate_data = ...          # (GreatExpectationsOperator — see Code_Example.md)

    # Task 2: Preprocess features (CPU container)
    preprocess = KubernetesPodOperator(
        task_id="preprocess_features",
        name="preprocess-{{ ds_nodash }}",
        namespace="ml-workloads",
        image="my-registry/ml-preprocess:1.0",
        env_vars={"PROCESSING_DATE": "{{ ds }}"},
        env_from=[k8s.V1EnvFromSource(
            secret_ref=k8s.V1SecretEnvSource(name="aws-credentials")
        )],
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "2", "memory": "8Gi"},
            limits={"cpu": "4",  "memory": "16Gi"},
        ),
        do_xcom_push=True,
        is_delete_operator_pod=True,
        get_logs=True,
        deferrable=True,
    )

    # Task 3: Train model (GPU container)
    train = KubernetesPodOperator(
        task_id="train_model",
        name="training-{{ ds_nodash }}",
        namespace="ml-workloads",
        image="my-registry/ml-training:1.0",
        env_vars={
            "PROCESSING_DATE": "{{ ds }}",
            "AIRFLOW_RUN_ID": "{{ run_id }}",
            "FEATURE_PATH": "{{ ti.xcom_pull('preprocess_features')['feature_path'] }}",
            "MLFLOW_TRACKING_URI": "http://mlflow-server:5000",
        },
        container_resources=k8s.V1ResourceRequirements(
            limits={"nvidia.com/gpu": "1", "memory": "32Gi", "cpu": "8"},
            requests={"nvidia.com/gpu": "1", "memory": "16Gi", "cpu": "4"},
        ),
        node_selector={"accelerator": "nvidia-tesla-t4"},
        tolerations=[k8s.V1Toleration(key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")],
        do_xcom_push=True,
        is_delete_operator_pod=True,
        get_logs=True,
        deferrable=True,
        execution_timeout=timedelta(hours=6),
    )

    # Task 4: Branch on accuracy
    def branch_on_accuracy(**context):
        metrics = context["ti"].xcom_pull(task_ids="train_model")
        r2 = metrics.get("r2_score", 0)
        print(f"R² score: {r2:.4f}, threshold: {ACCURACY_THRESHOLD}")
        return "register_model" if r2 >= ACCURACY_THRESHOLD else "quarantine_model"

    branch = BranchPythonOperator(
        task_id="evaluate_metrics",
        python_callable=branch_on_accuracy,
    )

    register = PythonOperator(
        task_id="register_model",
        python_callable=lambda **ctx: print("Registering model in MLflow registry..."),
    )

    quarantine = PythonOperator(
        task_id="quarantine_model",
        python_callable=lambda **ctx: print("Model below threshold — quarantining."),
    )

    validate_data >> preprocess >> train >> branch >> [register, quarantine]
```

---

## Step 6 — Verify the Run

```bash
airflow dags trigger ml_training_pipeline --exec-date 2024-01-15
```

In the UI:
- `preprocess_features` — logs show row count and feature path
- `train_model` — logs show R² score and MLflow run ID
- `evaluate_metrics` — routes to `register_model` or `quarantine_model`

Check MLflow UI:
```
http://mlflow-server:5000/#/experiments/order-value-prediction
```

---

## 📂 Navigation

| | |
|---|---|
| **Project Guide** | [Project_Guide.md](./Project_Guide.md) |
| **Full Code** | [Code_Example.md](./Code_Example.md) |
| **Parent: Advanced Projects** | [03_Advanced_Projects](../Readme.md) |
| **Previous: Multi-Source ETL** | [04_Multi_Source_ETL](../../02_Intermediate_Projects/04_Multi_Source_ETL/Project_Guide.md) |
| **Next: Event-Driven Asset Pipeline** | [06_Event_Driven_Asset_Pipeline](../06_Event_Driven_Asset_Pipeline/Project_Guide.md) |
