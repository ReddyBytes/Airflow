# Guide — ML Training Pipeline

---

## Before You Start

Read `01_MISSION.md` and `02_ARCHITECTURE.md`. Understand the XCom-through-pod mechanism and why `deferrable=True` matters before writing any DAG code.

You will need:

- A Kubernetes cluster reachable from your Airflow scheduler (local `kind` works fine)
- The `apache-airflow-providers-cncf-kubernetes` package installed
- Two Docker images pushed to a registry your cluster can pull from: one for preprocessing (CPU), one for training (GPU or CPU mock)

For local development without a GPU, build a mock training image that skips PyTorch and writes a canned `return.json`:

```python
# mock_train.py — runs inside a plain Python image
import json, os
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({
        "r2_score": 0.91,
        "val_loss": 0.042,
        "mlflow_run_id": "mock-run-id-001",
        "model_path": "s3://ml-pipeline-bucket/models/mock/",
    }, f)
print("Mock training complete. R2=0.91")
```

---

## Step 1 — Validate Training Data

The first task is a data quality gate. Use `GreatExpectationsOperator` if you have a GX project set up. If not, use a stub `PythonOperator` that checks the S3 file exists and has a minimum row count:

```python
@task
def validate_training_data(ds: str = None) -> None:
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook
    hook = S3Hook(aws_conn_id="aws_default")
    key = f"data/training/{ds}/data.parquet"
    if not hook.check_for_key(key, bucket_name="ml-pipeline-bucket"):
        raise FileNotFoundError(f"Training data not found: {key}")
    print(f"[validate] Training data confirmed at s3://ml-pipeline-bucket/{key}")
```

The goal: if training data is missing, fail fast before submitting a GPU pod.

---

## Step 2 — Preprocess Features (KPO)

Use `KubernetesPodOperator` with your preprocessing image. Key parameters:

```python
preprocess = KubernetesPodOperator(
    task_id="preprocess_features",
    name="preprocess-{{ ds_nodash }}-{{ task_instance.try_number }}",
    namespace="ml-workloads",
    image="my-registry/ml-preprocess:1.0",
    env_vars={
        "PROCESSING_DATE": "{{ ds }}",
        "S3_BUCKET": "ml-pipeline-bucket",
    },
    container_resources=k8s.V1ResourceRequirements(
        requests={"cpu": "2", "memory": "8Gi"},
        limits={"cpu": "4",  "memory": "16Gi"},
    ),
    do_xcom_push=True,      # ← reads /airflow/xcom/return.json when pod exits
    is_delete_operator_pod=True,  # ← clean up the pod after it finishes
    get_logs=True,          # ← stream pod logs to Airflow task logs
    deferrable=True,        # ← release worker slot while pod runs
)
```

Your preprocessing script must write `/airflow/xcom/return.json` before it exits:

```python
# Inside preprocess.py (running in the pod)
import json, os
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({"feature_path": output_path, "row_count": len(df)}, f)
```

---

## Step 3 — Train Model (KPO with GPU)

The training KPO needs GPU resources and must read the feature path from the preprocessing XCom. Pass it via Jinja in `env_vars`:

```python
train = KubernetesPodOperator(
    task_id="train_model",
    name="training-{{ ds_nodash }}-{{ task_instance.try_number }}",
    namespace="ml-workloads",
    image="my-registry/ml-training:cuda12.1-v1.0",
    env_vars={
        "PROCESSING_DATE": "{{ ds }}",
        "FEATURE_PATH": "{{ task_instance.xcom_pull('preprocess_features')['feature_path'] }}",
        "MLFLOW_TRACKING_URI": "http://mlflow-server:5000",
    },
    container_resources=k8s.V1ResourceRequirements(
        requests={"nvidia.com/gpu": "1", "cpu": "4",  "memory": "16Gi"},
        limits={"nvidia.com/gpu": "1",  "cpu": "8",  "memory": "32Gi"},
    ),
    node_selector={"accelerator": "nvidia-tesla-t4"},
    tolerations=[
        k8s.V1Toleration(key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")
    ],
    do_xcom_push=True,
    is_delete_operator_pod=True,
    get_logs=True,
    deferrable=True,
    execution_timeout=timedelta(hours=8),
)
```

---

## Step 4 — Branch on Accuracy

`BranchPythonOperator` returns the task ID of the branch to take:

```python
def branch_on_accuracy(**context) -> str:
    metrics = context["ti"].xcom_pull(task_ids="train_model") or {}
    r2 = metrics.get("r2_score", 0.0)
    print(f"[evaluate] R2={r2:.4f}, threshold={R2_THRESHOLD}")
    return "register_model" if r2 >= R2_THRESHOLD else "quarantine_model"

branch = BranchPythonOperator(
    task_id="evaluate_metrics",
    python_callable=branch_on_accuracy,
)
```

The skipped branch's task will appear as `skipped` (purple) in the UI — that is correct and expected.

---

## Step 5 — Register or Quarantine

**Register path** — promote the MLflow run to the registry and emit the Asset:

```python
register = PythonOperator(
    task_id="register_model",
    python_callable=register_model_in_mlflow,
    outlets=[MODEL_ASSET],  # ← triggers downstream serving DAG
)
```

**Quarantine path** — tag the MLflow run so it is easy to find and investigate later:

```python
quarantine = PythonOperator(
    task_id="quarantine_model",
    python_callable=quarantine_model_artifact,
    # No outlets — we do not want to trigger serving with a bad model
)
```

---

## Step 6 — Converge with Notify

```python
notify = PythonOperator(
    task_id="notify_team",
    python_callable=notify_team,
    trigger_rule="none_failed_min_one_success",  # ← runs regardless of which branch ran
)
```

Wire the dependencies:

```python
validate_training_data >> preprocess >> train >> branch
branch >> register   >> notify
branch >> quarantine >> notify
```

---

## Verify the Run

```bash
airflow dags trigger ml_training_pipeline --exec-date 2024-01-15
```

Check:
- `preprocess_features` logs show row count and feature path
- `train_model` logs show R2 score and MLflow run ID
- `evaluate_metrics` routes to the correct branch
- If registered: MLflow UI shows a new version in the `order-value-prediction` experiment
- If quarantined: MLflow run is tagged `status=quarantined`

---

## Common Issues

| Symptom | Likely cause | Fix |
|---|---|---|
| Pod stuck in `Pending` | No nodes match `node_selector` | Check cluster node labels: `kubectl get nodes --show-labels` |
| `return.json` not found | Script exited before writing XCom | Add try/finally around return.json write in train.py |
| `evaluate_metrics` gets `None` XCom | `do_xcom_push=False` | Set `do_xcom_push=True` on the training KPO |
| Both branches run | Missing `trigger_rule` on downstream tasks | Default `all_success` skips tasks after a branch — that is correct, verify UI shows purple |

---

⬅️ **Prev:** [04 — Multi-Source ETL](../04_Multi_Source_ETL/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
