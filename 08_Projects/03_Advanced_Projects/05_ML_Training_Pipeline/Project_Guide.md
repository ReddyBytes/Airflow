# 🔴 Project 05 — ML Training Pipeline

> **Level:** Advanced | **Est. Time:** 5–8 hours | **Skills:** KubernetesPodOperator, Assets (Airflow 3), BranchPythonOperator, Pools, Deferrable operators

---

## The Story

Your ML team has a training script that lives in a Docker image. It needs Python 3.11, PyTorch, and 32GB of RAM. Your Airflow workers have neither.

You've been running `docker run` manually to train the model, then copying the output to S3. It's fragile. When training fails at 3am, no one knows until morning. When a model performs poorly, it gets deployed anyway because there's no automated evaluation gate.

You need to:
1. Trigger training automatically when new data arrives
2. Run it in an isolated Kubernetes pod (not the Airflow workers)
3. Evaluate the trained model's accuracy via XCom
4. Automatically decide: good accuracy → register model → emit Asset to trigger serving pipeline; poor accuracy → alert team

This is a production ML pipeline.

---

## Architecture

```mermaid
flowchart TD
    subgraph Trigger["Trigger"]
        Asset[raw_data Asset\nfires when new data lands]
    end

    subgraph Pipeline["Airflow DAG — triggered by Asset"]
        subgraph Prep["Data Preparation"]
            Load[load_training_data\nS3 → preprocessing pod]
            Preprocess[preprocess_data\nKubernetesPodOperator\npython:3.11 image]
        end

        subgraph Train["Model Training"]
            Train[train_model\nKubernetesPodOperator\npytorch image\n32GB RAM, GPU]
        end

        subgraph Eval["Evaluation"]
            Eval[evaluate_model\nKubernetesPodOperator\nreads XCom metrics]
            Branch{accuracy ≥ 0.90?}
        end

        subgraph PassPath["✅ Good Model"]
            Register[register_model\nMLflow / SageMaker]
            EmitAsset[emit model_ready Asset\ntriggers serving DAG]
        end

        subgraph FailPath["❌ Poor Model"]
            Alert[send_alert\nSlack + email]
            Archive[archive_bad_model\nfor investigation]
        end
    end

    Asset --> Load
    Load --> Preprocess
    Preprocess --> Train
    Train --> Eval
    Eval --> Branch
    Branch -->|accuracy ≥ 0.90| Register
    Register --> EmitAsset
    Branch -->|accuracy < 0.90| Alert
    Alert --> Archive

    style Prep fill:#E3F2FD
    style Train fill:#FFF3E0
    style Eval fill:#E8F5E9
    style PassPath fill:#E8F5E9
    style FailPath fill:#FFEBEE
```

---

## Key Design Decisions

### Why KubernetesPodOperator for Training?

| Concern | Why KPO solves it |
|---------|-------------------|
| PyTorch requires Python 3.11 | Each pod uses its own Docker image |
| Training needs 32GB RAM + GPU | Set resource limits per pod |
| Airflow workers shouldn't run ML code | Complete isolation — pod dies after task |
| Training takes 45 min | Pod runs until done; Airflow just waits |
| One bad training run shouldn't affect other DAGs | Pod failure doesn't affect workers |

### Why Deferrable Operators?

Training takes 45 minutes. A regular KubernetesPodOperator holds a worker slot for the entire duration. With a **deferrable** KPO, the worker releases its slot after submitting the pod and only wakes up when the pod completes. This frees workers for other tasks during the 45-minute wait.

### XCom from the Training Pod

The training script writes metrics to `/airflow/xcom/return.json` before exiting. Airflow reads this and pushes to XCom. The evaluation task reads these metrics to decide if the model is good enough.

---

## Training Script Output (XCom)

Your training container (`train.py`) must write this file:

```python
# At the end of train.py — inside the training container
import json, os

metrics = {
    "accuracy": 0.943,
    "val_loss": 0.071,
    "f1_score": 0.938,
    "training_epochs": 50,
    "training_time_seconds": 2847,
    "model_artifact_path": "s3://ml-models/experiments/run-2024-01-15/model.pkl",
    "experiment_id": "exp-20240115-001",
}

os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump(metrics, f)

print(f"Training complete. Accuracy: {metrics['accuracy']:.3f}")
```

---

## Core Code Pattern: Training Task

```python
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

train_model = KubernetesPodOperator(
    task_id="train_model",

    # The training Docker image — your ML team maintains this
    image="your-ecr.amazonaws.com/ml-training:v2.1",
    image_pull_policy="Always",

    # Commands passed to the container
    cmds=["python", "/app/train.py"],
    arguments=[
        "--data-path", "/tmp/training_data/",
        "--output-dir", "/tmp/model_output/",
        "--epochs", "50",
        "--date", "{{ ds }}",
    ],

    # Read back /airflow/xcom/return.json as XCom
    do_xcom_push=True,

    # GPU node
    node_selector={"cloud.google.com/gke-nodepool": "gpu-training"},
    tolerations=[
        k8s.V1Toleration(key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")
    ],

    # 32GB RAM, 1 GPU
    container_resources=k8s.V1ResourceRequirements(
        requests={"memory": "32Gi", "cpu": "8", "nvidia.com/gpu": "1"},
        limits={"memory": "64Gi", "cpu": "16", "nvidia.com/gpu": "1"},
    ),

    # Release worker slot while pod runs (deferrable KPO)
    # Requires triggerer to be running
    deferrable=True,

    # Environment: AWS creds via IRSA, no hardcoded keys
    service_account_name="ml-training-sa",
    env_vars={
        "MLFLOW_TRACKING_URI": "http://mlflow.data-platform:5000",
        "EXECUTION_DATE": "{{ ds }}",
    },

    # Assign to pool to limit concurrent training runs
    pool="ml_training_pool",  # create with: airflow pools set ml_training_pool 2 ""
)
```

---

## Emitting a Model Asset (Airflow 3)

When the model passes evaluation, emit an Asset. This triggers the downstream serving DAG automatically — no polling, no manual triggers:

```python
from airflow.sdk import Asset

# Define the asset
model_ready_asset = Asset("model://churn-prediction/latest")

# Emit the asset in the register task
@task(outlets=[model_ready_asset])
def register_model(**context):
    metrics = context["ti"].xcom_pull(task_ids="train_model")
    model_path = metrics["model_artifact_path"]

    # Register in MLflow (or SageMaker Model Registry, etc.)
    import mlflow
    mlflow.register_model(model_path, "churn-prediction")

    print(f"Model registered: {model_path}")
    print(f"Accuracy: {metrics['accuracy']}")

    # Returning from an @task with outlets= emits the asset automatically
    return {"model_path": model_path, "accuracy": metrics["accuracy"]}
```

The downstream serving DAG is triggered automatically:
```python
# In the serving DAG
with DAG(
    dag_id="model_serving_update",
    schedule=[model_ready_asset],   # Triggered when this asset is emitted
    ...
):
    deploy_model = KubernetesPodOperator(...)
```

---

## Pool Configuration

```bash
# Limit to 2 concurrent ML training runs
airflow pools set ml_training_pool 2 "Limits parallel model training jobs"

# Limit GPU node requests
airflow pools set gpu_pool 4 "Limits GPU pod submissions"
```

---

## What You'll Learn

| Skill | Where it appears |
|-------|-----------------|
| KubernetesPodOperator | Running training in an isolated pod with GPU |
| `deferrable=True` | Releasing worker slots during long-running pods |
| `do_xcom_push=True` | Reading metrics from `/airflow/xcom/return.json` |
| Assets (Airflow 3) | Emitting `model_ready_asset` to trigger serving DAG |
| BranchPythonOperator | Routing on model accuracy threshold |
| Pools | Limiting concurrent training jobs |
| `on_failure_callback` | Alerting when training fails |

---

## Expected Output

**Happy path:**
```
Task: load_training_data        → SUCCESS — 500,000 rows
Task: preprocess_data [KPO]     → SUCCESS — features engineered
Task: train_model [KPO, GPU]    → SUCCESS — accuracy: 0.943 (took 47 min)
Task: evaluate_model            → SUCCESS — accuracy 0.943 ≥ threshold 0.90
Task: branch                    → routes to "register_model"
Task: register_model            → SUCCESS — churn-prediction v15 registered
Task: emit_model_asset          → SUCCESS — model_ready_asset emitted
                                            Serving DAG triggered automatically
```

**Poor model path:**
```
Task: train_model [KPO]         → SUCCESS — accuracy: 0.812
Task: evaluate_model            → SUCCESS — accuracy 0.812 < threshold 0.90
Task: branch                    → routes to "alert_poor_model"
Task: alert_poor_model          → SUCCESS
Slack: 🔴 Model accuracy 0.812 below threshold 0.90. Run archived.
```

---

## Extension Challenges

1. **Hyperparameter sweep** — use `expand()` to train 5 models in parallel with different learning rates; keep the best
2. **Add a data drift check** — compare training data distribution to last month before training
3. **A/B testing** — emit the asset with metadata; serving DAG runs 10% traffic to new model first
4. **Model lineage** — log the training data Asset as an inlet to the model Asset

---

## See Also

- [Event-Driven Asset Pipeline →](../06_Event_Driven_Asset_Pipeline/Project_Guide.md) — The full asset-driven pattern
- [KubernetesPodOperator Deep Dive →](../../../07_Integrations/44_KubernetesPodOperator_Deep_Dive/Theory.md) — All KPO parameters
