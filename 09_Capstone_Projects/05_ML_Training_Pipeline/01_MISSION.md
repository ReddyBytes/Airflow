# Project 05 — ML Training Pipeline

> **Difficulty:** 🟠 Minimal Hints &nbsp;&nbsp; **Level:** Advanced &nbsp;&nbsp; **Est. Time:** 5–8 hours
>
> **Skills you will use:** KubernetesPodOperator, deferrable operators, `do_xcom_push`, Assets (Airflow 3), BranchPythonOperator, Pools

---

## The Situation

Your ML team has a training script. It needs Python 3.11, PyTorch, and 32 GB of RAM. Your Airflow workers have none of those things.

Right now someone runs `docker run` manually to kick off training, then copies the output to S3. When training fails at 3am, no one knows until morning. When a model performs poorly, it gets deployed anyway because there is no automated evaluation gate.

You need to:

1. Trigger training automatically when new feature data arrives
2. Run it in an isolated Kubernetes pod — not on the Airflow workers
3. Read the trained model's accuracy back via XCom
4. Automatically decide: good accuracy goes to model registration and emits an Asset to trigger the serving pipeline; poor accuracy fires a Slack alert

---

## What You Need to Build

```
validate_training_data  (Great Expectations checkpoint)
         |
         v
preprocess_features     (KubernetesPodOperator — CPU container)
         |
         v
train_model             (KubernetesPodOperator — GPU container, deferrable)
         |
         v
evaluate_metrics        (BranchPythonOperator — reads R2 from XCom)
        / \
       /   \
register  quarantine
 _model   _model
    \       /
     \     /
    notify_team         (trigger_rule: none_failed_min_one_success)
```

---

## Key Concepts in Play

**KubernetesPodOperator** runs each step in its own container. The preprocessing step uses a plain Python 3.11 image. The training step uses a CUDA-enabled PyTorch image with GPU node selectors. The Airflow workers never touch ML code.

**Deferrable operators** matter for the 45-minute training job. A regular KPO holds a worker slot for the entire wait. With `deferrable=True`, the worker releases its slot after pod submission and only wakes when the pod completes. This frees your workers for other DAGs during the wait.

**XCom from a pod** works through a sidecar convention: your training script writes metrics to `/airflow/xcom/return.json` before it exits. Set `do_xcom_push=True` on the KPO and Airflow reads that file automatically.

```python
# At the end of train.py — inside the training container
import json, os
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({"r2_score": 0.91, "val_loss": 0.042, ...}, f)
```

**BranchPythonOperator** reads the R2 score from XCom and returns either `"register_model"` or `"quarantine_model"`. Airflow skips the branch not returned.

**Assets** — `register_model` declares `outlets=[MODEL_ASSET]`. When it succeeds, the serving DAG triggers automatically. No `TriggerDagRunOperator`, no polling.

---

## Acceptance Criteria

By the end of this project your DAG must:

1. Use `GreatExpectationsOperator` (or a stub `PythonOperator`) for data validation
2. Use `KubernetesPodOperator` with `deferrable=True` for preprocessing and training
3. Pass the feature path from preprocessing to training via XCom + Jinja in `env_vars`
4. Use `BranchPythonOperator` to route on R2 threshold (default: 0.85)
5. `register_model` task has `outlets=[MODEL_ASSET]`
6. `quarantine_model` tags the MLflow run as quarantined (or logs the decision)
7. `notify_team` converges both branches with `trigger_rule="none_failed_min_one_success"`

---

## Extension Challenges

1. Hyperparameter sweep — use `expand()` to train 5 models in parallel with different learning rates; keep the best one
2. Add a data drift check between validation and training steps
3. Attach accuracy metadata to the Asset so consumers know the model quality before running
4. Add `on_failure_callback` to the training task that posts to Slack on KPO failure

---

⬅️ **Prev:** [04 — Multi-Source ETL](../04_Multi_Source_ETL/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
