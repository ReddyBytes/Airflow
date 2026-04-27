# Recap — ML Training Pipeline

---

## What You Built

An end-to-end ML training pipeline that validates training data, preprocesses features in a CPU container, trains a model in a GPU container, branches on accuracy threshold, registers good models in MLflow and emits an Asset to trigger the serving pipeline, and quarantines poor models with clear tagging for investigation. All ML steps run in isolated Kubernetes pods — the Airflow workers only orchestrate.

---

## Skills Demonstrated

**KubernetesPodOperator**

Every ML step runs in its own container with the exact image and resource specification it needs. The Airflow worker never executes ML code. Pod failure is isolated — it cannot affect other DAGs or workers.

Key parameters to remember:
- `do_xcom_push=True` — reads `/airflow/xcom/return.json` on pod exit, pushes to XCom
- `is_delete_operator_pod=True` — cleans up the pod after it finishes
- `deferrable=True` — releases the worker slot while the pod runs

**Deferrable operators**

A 45-minute training job held a worker slot for 45 minutes in older Airflow. With `deferrable=True`, the worker submits the pod, suspends, and the Airflow triggerer wakes it when the pod completes. Those 45 minutes of worker capacity are freed for other tasks.

**XCom through a pod**

The contract: write `{"key": "value"}` to `/airflow/xcom/return.json` before the script exits. The KPO's sidecar reads this file and pushes it to XCom. The downstream branch task reads it with `context["ti"].xcom_pull(task_ids="train_model")`.

```python
# At the end of train.py — inside the container
import json, os
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({"r2_score": 0.91, "mlflow_run_id": "abc123"}, f)
```

**BranchPythonOperator**

Returns a task ID string. Airflow runs that task and marks all other branches `skipped`. The skipped state is correct and expected — do not confuse it with a failure.

**Assets as integration glue**

`register_model` declares `outlets=[MODEL_ASSET]`. The downstream serving DAG has `schedule=[MODEL_ASSET]`. When a good model is registered, the serving DAG fires. No `TriggerDagRunOperator`. No polling. No hard coupling between the two DAGs.

---

## Common Mistakes Made Here

**Mistake: `do_xcom_push` defaults to False on KPO**

If `do_xcom_push=True` is omitted, the XCom is never pushed and `branch_on_model_accuracy` pulls `None` — the branch defaults to quarantine regardless of actual accuracy. Always set it explicitly.

**Mistake: `trigger_rule` not set on `notify_team`**

Default `all_success` on `notify_team` means it is skipped whenever one branch is skipped. Set `trigger_rule="none_failed_min_one_success"` so notify always runs after either branch completes.

**Mistake: FEATURE_PATH not passed via Jinja**

If the feature path is hardcoded, rerunning for a different date uses the wrong S3 partition. Pass it dynamically:

```python
"FEATURE_PATH": "{{ task_instance.xcom_pull('preprocess_features')['feature_path'] }}"
```

---

## How This Connects to Real Work

KubernetesPodOperator is the standard pattern for running heavy workloads (ML training, Spark jobs, data quality frameworks) from Airflow. The pod isolation, per-task GPU allocation, and deferrable wait model are all production patterns used in real ML platforms.

The branching + Asset emission pattern is how ML platforms decouple training pipelines from serving pipelines. The serving team subscribes to `MODEL_ASSET` and their DAG fires automatically — without needing to know anything about the training pipeline's internals.

---

## What to Try Next

Extend the pipeline with a hyperparameter sweep: use `expand()` to train 5 models in parallel with different learning rates. Add a `select_best_model` task after the fan-out that reads all five XCom results and routes the best one to registration.

---

✅ **Completed:** KubernetesPodOperator, deferrable operators, XCom from pods, BranchPythonOperator, Asset outlets, converging branches

🔨 **Practice:** Replace the accuracy branch threshold with a dynamic variable (`Variable.get("r2_threshold", default_var="0.85")`) so it can be tuned without a DAG deploy

➡️ **Next project:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md) — pure Asset-driven scheduling across multiple DAGs

---

⬅️ **Prev:** [04 — Multi-Source ETL](../04_Multi_Source_ETL/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [06 — Event-Driven Asset Pipeline](../06_Event_Driven_Asset_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
