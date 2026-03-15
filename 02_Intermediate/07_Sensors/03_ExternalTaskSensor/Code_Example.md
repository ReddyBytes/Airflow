# ExternalTaskSensor — Code Examples

## Example 1: Wait for an Entire DAG Run to Complete

The most common use case: DAG B starts processing only after DAG A has fully finished for the same day.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.operators.python import PythonOperator

# ============================================================
# UPSTREAM DAG: data_ingestion (runs at midnight daily)
# ============================================================
with DAG(
    dag_id="data_ingestion",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 0 * * *",   # Midnight
    catchup=False,
    tags=["upstream", "ingestion"],
) as ingestion_dag:

    def ingest_sales(**context):
        print(f"Ingesting sales data for {context['ds']}")
        # ... actual ingestion logic

    def ingest_customers(**context):
        print(f"Ingesting customer data for {context['ds']}")

    def validate_all(**context):
        print(f"All ingestion complete and validated for {context['ds']}")

    ingest_sales_task = PythonOperator(
        task_id="ingest_sales",
        python_callable=ingest_sales,
    )

    ingest_customers_task = PythonOperator(
        task_id="ingest_customers",
        python_callable=ingest_customers,
    )

    validate_task = PythonOperator(
        task_id="validate_all_data",
        python_callable=validate_all,
    )

    [ingest_sales_task, ingest_customers_task] >> validate_task


# ============================================================
# DOWNSTREAM DAG: daily_reporting (runs at 2am daily)
# Both run daily — execution dates align, no execution_delta needed
# ============================================================
with DAG(
    dag_id="daily_reporting",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 2 * * *",   # 2am — gives ingestion 2 hours to run
    catchup=False,
    tags=["downstream", "reporting"],
) as reporting_dag:

    # Wait for the entire data_ingestion DAG to complete
    wait_for_ingestion = ExternalTaskSensor(
        task_id="wait_for_data_ingestion",
        external_dag_id="data_ingestion",
        external_task_id=None,          # None = wait for the entire DAG run
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        poke_interval=60,               # Check every minute
        timeout=4 * 60 * 60,           # Give up after 4 hours
        mode="reschedule",
    )

    def generate_report(**context):
        print(f"All upstream data confirmed. Generating report for {context['ds']}")

    generate = PythonOperator(
        task_id="generate_daily_report",
        python_callable=generate_report,
    )

    wait_for_ingestion >> generate
```

**What to notice:**
- Both DAGs run daily. The reporting DAG starts at 2am, giving ingestion a 2-hour window.
- `external_task_id=None` waits for the entire `data_ingestion` DAG run — all tasks must succeed.
- `failed_states=["failed", "upstream_failed"]` ensures fast failure if ingestion breaks.

---

## Example 2: Wait for a Specific Task with execution_delta

DAG A runs hourly. DAG B runs daily and needs DAG A's 11pm run (the last of the day) to complete before proceeding.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.operators.python import PythonOperator

# ============================================================
# UPSTREAM DAG: hourly_data_loader (runs every hour)
# ============================================================
with DAG(
    dag_id="hourly_data_loader",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@hourly",
    catchup=False,
) as hourly_dag:

    def load_hourly(**context):
        print(f"Loading data for execution_date: {context['execution_date']}")

    load_data = PythonOperator(
        task_id="load_data",
        python_callable=load_hourly,
    )


# ============================================================
# DOWNSTREAM DAG: daily_aggregation (runs at midnight daily)
# ============================================================
with DAG(
    dag_id="daily_aggregation",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",    # Midnight (2024-01-15 00:00)
    catchup=False,
) as daily_dag:

    # Daily DAG execution date: 2024-01-15 00:00:00
    # Hourly DAG 11pm run execution date: 2024-01-14 23:00:00
    # Difference: 1 hour → execution_delta=timedelta(hours=1)

    wait_for_last_hourly_run = ExternalTaskSensor(
        task_id="wait_for_last_hourly_load",
        external_dag_id="hourly_data_loader",
        external_task_id="load_data",
        execution_delta=timedelta(hours=1),
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        poke_interval=60,
        timeout=3 * 60 * 60,
        mode="reschedule",
    )

    def aggregate(**context):
        print(f"Hourly data complete. Running daily aggregation for {context['ds']}")

    run_aggregation = PythonOperator(
        task_id="run_daily_aggregation",
        python_callable=aggregate,
    )

    wait_for_last_hourly_run >> run_aggregation
```

---

## Example 3: Wait for All Hourly Runs Using execution_date_fn

When you need all N runs from the upstream DAG (not just the most recent) to complete before proceeding.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.operators.python import PythonOperator


def get_all_24_hourly_runs(dt):
    """
    For a daily DAG running at midnight (execution_date = previous midnight),
    return execution dates for all 24 hourly runs of that day.

    Example:
      dt = 2024-01-15 00:00:00
      Returns: [2024-01-14 23:00, 2024-01-14 22:00, ..., 2024-01-14 00:00]
    """
    return [dt - timedelta(hours=h) for h in range(1, 25)]


with DAG(
    dag_id="daily_full_aggregation",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
) as dag:

    # Wait for ALL 24 hourly runs to complete
    wait_for_all_hourly = ExternalTaskSensor(
        task_id="wait_for_all_hourly_loads",
        external_dag_id="hourly_data_loader",
        external_task_id="load_data",
        execution_date_fn=get_all_24_hourly_runs,
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        poke_interval=120,
        timeout=6 * 60 * 60,
        mode="reschedule",
    )

    def run_full_day_aggregation(**context):
        print(f"All 24 hourly loads confirmed complete for {context['ds']}")
        print("Running full-day aggregation...")

    aggregate = PythonOperator(
        task_id="full_day_aggregation",
        python_callable=run_full_day_aggregation,
    )

    wait_for_all_hourly >> aggregate
```

---

## Example 4: With failed_states for Immediate Error Detection

Without `failed_states`, the sensor keeps waiting even if the upstream DAG already failed — you waste time until timeout. Always set `failed_states` in production.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.operators.python import PythonOperator


def alert_on_upstream_failure(context):
    """Called when the sensor fails because the upstream DAG failed."""
    print(f"ALERT: Upstream pipeline failed! Context: {context['task_instance']}")
    # In production: send Slack message, PagerDuty alert, etc.


with DAG(
    dag_id="critical_downstream_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args={
        "on_failure_callback": alert_on_upstream_failure,
        "retries": 0,  # Don't retry if upstream failed — it needs human intervention
    },
) as dag:

    # Fail immediately if upstream is in a terminal failure state
    wait_for_critical_upstream = ExternalTaskSensor(
        task_id="wait_for_critical_pipeline",
        external_dag_id="critical_ingestion_pipeline",
        external_task_id="final_validation",
        allowed_states=["success"],
        failed_states=[
            "failed",
            "upstream_failed",
            "skipped",       # Treat skipped as a problem in critical paths
        ],
        poke_interval=60,
        timeout=4 * 60 * 60,
        mode="reschedule",
        soft_fail=False,    # Hard fail — do not skip downstream
        on_failure_callback=alert_on_upstream_failure,
    )

    def run_critical_job(**context):
        print("Critical upstream confirmed. Running downstream job...")

    critical_job = PythonOperator(
        task_id="critical_downstream_job",
        python_callable=run_critical_job,
    )

    wait_for_critical_upstream >> critical_job
```

---

## Example 5: Multiple Parallel Sensors + Graceful Optional Dependency

Wait for two required upstream DAGs plus one optional upstream DAG. Proceed even if the optional one hasn't run.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.operators.python import PythonOperator


with DAG(
    dag_id="multi_source_report",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
) as dag:

    # Required: both must succeed
    wait_for_sales = ExternalTaskSensor(
        task_id="wait_for_sales_data",
        external_dag_id="sales_pipeline",
        external_task_id=None,
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        poke_interval=60, timeout=7200, mode="reschedule",
        soft_fail=False,  # Hard fail — sales data is required
    )

    wait_for_finance = ExternalTaskSensor(
        task_id="wait_for_finance_data",
        external_dag_id="finance_pipeline",
        external_task_id=None,
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        poke_interval=60, timeout=7200, mode="reschedule",
        soft_fail=False,  # Hard fail — finance data is required
    )

    # Optional: best-effort, skip if not available
    wait_for_enrichment = ExternalTaskSensor(
        task_id="wait_for_enrichment_data",
        external_dag_id="optional_enrichment_pipeline",
        external_task_id=None,
        allowed_states=["success"],
        poke_interval=120, timeout=3600, mode="reschedule",
        soft_fail=True,   # Skip if not available — report proceeds without enrichment
    )

    def generate_multi_source_report(**context):
        import os
        print("Generating report from available data sources...")
        # Sales and finance are guaranteed by the required sensors
        # Enrichment may or may not be available (sensor soft_fail=True)

    generate = PythonOperator(
        task_id="generate_report",
        python_callable=generate_multi_source_report,
        trigger_rule="none_failed",  # Run even if enrichment sensor was skipped
    )

    # Run all three sensors in parallel
    [wait_for_sales, wait_for_finance, wait_for_enrichment] >> generate
```

**What to notice:**
- Required sensors use `soft_fail=False` — pipeline won't proceed without sales and finance data.
- Optional sensor uses `soft_fail=True` — if enrichment data doesn't arrive, the pipeline continues with what it has.
- `trigger_rule="none_failed"` on the report task means "run as long as no upstream tasks failed (skipped is okay)."
- All three sensors run in parallel — the total wait time is the max of the three, not their sum.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview questions |
| 💻 **Code_Example.md** | ← you are here |

⬅️ **Prev:** [HttpSensor](../02_HttpSensor/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [S3KeySensor](../04_S3KeySensor/Theory.md)
