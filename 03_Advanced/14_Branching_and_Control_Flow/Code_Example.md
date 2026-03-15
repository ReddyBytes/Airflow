# 10 — Branching and Control Flow: Code Examples

## Example 1 — BranchPythonOperator with Two Branches

```python
from airflow import DAG
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.utils.trigger_rule import TriggerRule
from datetime import datetime

def check_data_quality(ti, **context):
    # Simulate a quality score (0.0 – 1.0)
    score = 0.97
    ti.xcom_push(key="quality_score", value=score)

def decide_path(ti, **context):
    score = ti.xcom_pull(task_ids="check_quality", key="quality_score")
    if score >= 0.95:
        return "load_to_production"
    return "send_quality_alert"

def load_to_production():
    print("Data is clean — loading to production table.")

def send_quality_alert():
    print("Quality below threshold — sending alert to Slack.")

def update_audit_log():
    # Must run after EITHER branch — use NONE_FAILED trigger rule
    print("Audit log updated.")

with DAG(
    dag_id="branch_two_paths",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    check_quality = PythonOperator(
        task_id="check_quality",
        python_callable=check_data_quality,
    )

    branch = BranchPythonOperator(
        task_id="quality_decision",
        python_callable=decide_path,
    )

    load = PythonOperator(task_id="load_to_production", python_callable=load_to_production)
    alert = PythonOperator(task_id="send_quality_alert", python_callable=send_quality_alert)

    audit = PythonOperator(
        task_id="update_audit_log",
        python_callable=update_audit_log,
        trigger_rule=TriggerRule.NONE_FAILED,  # runs after either branch
    )

    check_quality >> branch
    branch >> [load, alert]
    [load, alert] >> audit
```

---

## Example 2 — ShortCircuitOperator for a Quality Gate

```python
from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from datetime import datetime

def run_validations(ti):
    # Simulate a validation check
    row_count = 15_000
    null_pct   = 0.02
    ti.xcom_push(key="row_count", value=row_count)
    ti.xcom_push(key="null_pct",  value=null_pct)
    print(f"Rows: {row_count}, Null%: {null_pct:.1%}")

def is_data_valid(ti, **context):
    row_count = ti.xcom_pull(task_ids="validate_data", key="row_count")
    null_pct   = ti.xcom_pull(task_ids="validate_data", key="null_pct")

    if row_count < 1:
        print("GATE: No rows found — short-circuiting pipeline")
        return False
    if null_pct > 0.10:
        print(f"GATE: Null% too high ({null_pct:.1%}) — short-circuiting pipeline")
        return False

    print("GATE: Data looks good — proceeding")
    return True

def load_data():
    print("Loading data to warehouse...")

def generate_report():
    print("Report generated.")

with DAG(
    dag_id="short_circuit_gate",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    validate  = PythonOperator(task_id="validate_data",    python_callable=run_validations)
    gate      = ShortCircuitOperator(task_id="quality_gate", python_callable=is_data_valid)
    load      = PythonOperator(task_id="load_data",         python_callable=load_data)
    report    = PythonOperator(task_id="generate_report",   python_callable=generate_report)

    # If gate returns False, both load and generate_report are SKIPPED
    validate >> gate >> load >> report
```

---

## Example 3 — TriggerRule.ONE_FAILED for an Alert Task

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.utils.trigger_rule import TriggerRule
from datetime import datetime

def extract():
    print("Extracting data...")

def transform():
    print("Transforming data...")
    # Uncomment to simulate a failure:
    # raise ValueError("Transform failed!")

def load():
    print("Loading data...")

with DAG(
    dag_id="trigger_rule_one_failed",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
) as dag:

    t_extract   = PythonOperator(task_id="extract",   python_callable=extract)
    t_transform = PythonOperator(task_id="transform", python_callable=transform)
    t_load      = PythonOperator(task_id="load",      python_callable=load)

    # This alert fires as soon as ANY of the three tasks above fails
    alert = EmailOperator(
        task_id="send_failure_alert",
        to="data-team@example.com",
        subject="Pipeline {{ dag.dag_id }} failed on {{ ds }}",
        html_content="<p>One or more tasks failed. Please investigate.</p>",
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    # alert is downstream of all three tasks
    [t_extract, t_transform, t_load] >> alert
    t_extract >> t_transform >> t_load
```

---

## Example 4 — Full DAG: Branch + Join + Conditional Notification

```python
from airflow import DAG
from airflow.operators.python import BranchPythonOperator, PythonOperator, ShortCircuitOperator
from airflow.utils.trigger_rule import TriggerRule
from airflow.models import Variable
from datetime import datetime

# ── Helper callables ──────────────────────────────────────────────────────────

def ingest_data(ti):
    rows = 50_000
    ti.xcom_push(key="rows", value=rows)
    print(f"Ingested {rows} rows")

def is_data_present(ti, **context):
    rows = ti.xcom_pull(task_ids="ingest", key="rows")
    return rows > 0   # short-circuit if nothing came in

def decide_environment():
    env = Variable.get("environment", default_var="staging")
    return f"load_{env}"      # "load_production" or "load_staging"

def load_production():
    print("Loading to PRODUCTION table")

def load_staging():
    print("Loading to STAGING table")

def notify_success():
    print("Sending success notification")

def notify_failure():
    print("Sending failure/alert notification")

def finalize():
    print("Pipeline complete — writing audit record")

# ── DAG definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="full_branch_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:

    ingest = PythonOperator(task_id="ingest", python_callable=ingest_data)

    # Gate: stop the whole pipeline if no rows arrived
    data_gate = ShortCircuitOperator(
        task_id="data_gate",
        python_callable=is_data_present,
    )

    # Branch: route to the correct environment
    env_branch = BranchPythonOperator(
        task_id="env_branch",
        python_callable=decide_environment,
    )

    t_prod    = PythonOperator(task_id="load_production", python_callable=load_production)
    t_staging = PythonOperator(task_id="load_staging",    python_callable=load_staging)

    # Success notification — runs after either load task succeeds
    success_notify = PythonOperator(
        task_id="notify_success",
        python_callable=notify_success,
        trigger_rule=TriggerRule.NONE_FAILED,
    )

    # Failure notification — runs if any task in the pipeline fails
    failure_notify = PythonOperator(
        task_id="notify_failure",
        python_callable=notify_failure,
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    # Final audit — runs after everything (success or failure)
    audit = PythonOperator(
        task_id="finalize",
        python_callable=finalize,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # Wire it all together
    ingest >> data_gate >> env_branch
    env_branch >> [t_prod, t_staging]
    [t_prod, t_staging] >> success_notify
    [ingest, data_gate, t_prod, t_staging] >> failure_notify
    [success_notify, failure_notify] >> audit
```
