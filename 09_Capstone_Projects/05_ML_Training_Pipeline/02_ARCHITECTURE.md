# Architecture — ML Training Pipeline

---

## The Problem This Solves

Running an ML training script on an Airflow worker is a category error. Workers are shared, stateless, and sized for orchestration work — not for PyTorch with 32 GB of RAM and a GPU. The moment training starts, the worker is saturated, other tasks queue behind it, and any failure brings down work that has nothing to do with ML.

The solution is to move every ML step into its own Kubernetes pod. The Airflow worker submits the pod and either holds its slot waiting (blocking) or releases the slot and waits for a completion event (deferrable). Each pod uses the exact image it needs — CUDA-enabled for training, plain Python for preprocessing.

---

## Task Dependency Graph

```
validate_training_data
(GreatExpectationsOperator — fail fast before spending GPU budget)
         |
         v
preprocess_features
(KubernetesPodOperator, CPU image, deferrable=True)
(writes feature_path to /airflow/xcom/return.json)
         |
         v
train_model
(KubernetesPodOperator, GPU image, deferrable=True)
(reads FEATURE_PATH from env via Jinja+XCom)
(writes r2_score, val_loss, mlflow_run_id to /airflow/xcom/return.json)
         |
         v
evaluate_metrics
(BranchPythonOperator — reads r2_score from XCom)
        / \
       /   \
      v     v
register  quarantine
 _model    _model
(outlets=  (tags MLflow
MODEL_ASSET) run as quarantined)
       \     /
        \   /
         v v
      notify_team
(trigger_rule: none_failed_min_one_success)
```

---

## Data Flow: XCom Through Pods

The pods and the Airflow metadata database communicate through a sidecar convention. Each pod script writes a file at `/airflow/xcom/return.json` before it exits. The KubernetesPodOperator reads this file via an init container and pushes the contents to XCom automatically when `do_xcom_push=True` is set.

```
preprocess.py (inside pod)           Airflow
---------------------------------    -----------------------
Reads S3 training data
Engineers features
Writes features back to S3
Writes return.json:                  KPO reads return.json
  {"feature_path": "s3://...",  -->  pushes to XCom as
   "row_count": 450000}              task_instance.xcom_pull("preprocess_features")


train.py (inside pod)
---------------------------------
Reads FEATURE_PATH from env var      (Jinja pulls from preprocess XCom)
Trains PyTorch model
Logs metrics to MLflow
Writes return.json:                  KPO reads return.json
  {"r2_score": 0.91,             -->  pushed to XCom as
   "val_loss": 0.042,                 task_instance.xcom_pull("train_model")
   "mlflow_run_id": "abc123",
   "model_path": "s3://..."}
```

The Jinja expression that passes the feature path to the training container:

```python
"FEATURE_PATH": "{{ task_instance.xcom_pull('preprocess_features')['feature_path'] }}"
```

---

## Key Design Choices

**Why deferrable KPO?**

Training takes 45 minutes. A standard KPO holds a worker slot for the entire duration. With `deferrable=True`, the worker submits the pod, suspends itself, and releases its slot. The Airflow triggerer watches the pod. When it completes, the triggerer wakes the worker. During those 45 minutes, other tasks use the freed worker slot.

**Why BranchPythonOperator over conditional logic in the training task?**

Branching at the DAG level makes the decision visible. You can see in the UI which path each run took, when it branched, and why. Logic buried inside a task function is invisible to Airflow's graph and history.

**Why `trigger_rule="none_failed_min_one_success"` on `notify_team`?**

Standard `all_success` would fail if one branch was skipped. The notify task needs to run regardless of which branch was taken — it just needs at least one upstream to have succeeded.

**Why an Asset outlet instead of triggering the serving DAG directly?**

`TriggerDagRunOperator` is a hard coupling — the ML pipeline has to know the serving DAG's ID. An Asset outlet decouples them. The serving DAG subscribes to `MODEL_ASSET` and fires whenever any pipeline emits it. The ML pipeline has no knowledge of its consumers.

---

## Infrastructure Requirements

| Requirement | Detail |
|---|---|
| Kubernetes cluster | EKS, GKE, or local `kind` |
| GPU node pool | Node selector: `accelerator: nvidia-tesla-t4` |
| Container registry | ECR or GCR with `preprocess` and `training` images |
| MLflow tracking server | `http://mlflow-server:5000` reachable from pods |
| S3 bucket | `ml-pipeline-bucket` with `data/`, `models/` prefixes |

---

## Airflow Connections and Secrets Required

| Name | Type | Used by |
|---|---|---|
| `kubernetes_default` | Kubernetes | KubernetesPodOperator |
| `aws_default` | Amazon S3 | Preprocessing and training pods (via IRSA) |
| K8s secret `aws-credentials` | Kubernetes Secret | Mounted as env into pods |
| K8s secret `mlflow-credentials` | Kubernetes Secret | Mounted as env into training pod |

---

⬅️ **Prev:** [04 — Multi-Source ETL](../04_Multi_Source_ETL/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
