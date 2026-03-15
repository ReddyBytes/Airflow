# TriggerDagRunOperator — Code Examples

## Example 1: Simple Trigger

Trigger another DAG with no waiting — fire and forget.

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.operators.empty import EmptyOperator


# =============================================================================
# PARENT DAG: orchestrator that triggers sub-pipelines
# =============================================================================
with DAG(
    dag_id="orchestrator_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    description="Master orchestrator that fires downstream pipelines",
    tags=["orchestrator", "trigger", "example"],
) as orchestrator:

    start = EmptyOperator(task_id="pipeline_start")

    def run_preflight_checks(**context):
        """Check that required data is ready before triggering sub-pipelines."""
        print(f"Running preflight checks for {context['ds']}")
        # Check S3 for expected input files
        # Check DB connections
        # Validate date range
        print("All checks passed — ready to trigger sub-pipelines")

    preflight = PythonOperator(
        task_id="preflight_checks",
        python_callable=run_preflight_checks,
    )

    # Trigger the reporting pipeline — don't wait for it
    trigger_reporting = TriggerDagRunOperator(
        task_id="trigger_reporting_pipeline",
        trigger_dag_id="daily_reporting_pipeline",   # Must match dag_id exactly
        conf={
            "triggered_by": "orchestrator_dag",
            "date": "{{ ds }}",
            "environment": "production",
        },
        wait_for_completion=False,   # Fire and forget
        reset_dag_run=True,          # Re-run if already exists (idempotent)
    )

    # Trigger data quality checks in parallel with reporting
    trigger_dq = TriggerDagRunOperator(
        task_id="trigger_data_quality",
        trigger_dag_id="data_quality_pipeline",
        conf={"date": "{{ ds }}", "tables": ["orders", "customers", "products"]},
        wait_for_completion=False,
    )

    end = EmptyOperator(task_id="pipeline_end")

    start >> preflight >> [trigger_reporting, trigger_dq] >> end


# =============================================================================
# CHILD DAG: the reporting pipeline (only runs when triggered)
# =============================================================================
with DAG(
    dag_id="daily_reporting_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,   # IMPORTANT: None means only runs via trigger
    catchup=False,
    tags=["reporting", "child", "example"],
) as reporting:

    def build_reports(**context):
        """Build daily reports. Access config passed from parent."""
        dag_run = context["dag_run"]

        # Access conf values from the triggering DAG
        trigger_date = dag_run.conf.get("date", context["ds"])
        environment = dag_run.conf.get("environment", "development")
        triggered_by = dag_run.conf.get("triggered_by", "manual")

        print(f"Building reports for {trigger_date}")
        print(f"Environment: {environment}")
        print(f"Triggered by: {triggered_by}")

        # Your report generation logic here
        reports_generated = ["executive_summary", "regional_breakdown", "product_analysis"]
        print(f"Generated {len(reports_generated)} reports")
        return reports_generated

    generate_reports = PythonOperator(
        task_id="generate_daily_reports",
        python_callable=build_reports,
    )
```

---

## Example 2: Trigger with conf and wait_for_completion=True

Wait for the child DAG to complete before continuing. Pass data through conf and use the result.

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.operators.empty import EmptyOperator


# =============================================================================
# CHILD DAG: ETL pipeline for a single customer
# =============================================================================
with DAG(
    dag_id="customer_etl_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,   # Only triggered externally
    catchup=False,
    tags=["etl", "customer", "child"],
) as customer_etl:

    def extract_customer_data(**context):
        dag_run = context["dag_run"]
        customer_id = dag_run.conf.get("customer_id")
        date = dag_run.conf.get("date", context["ds"])
        region = dag_run.conf.get("region", "US")

        print(f"[Customer {customer_id}] Extracting data for {date} (region={region})")
        # Simulate extraction
        records = [{"id": i, "customer": customer_id} for i in range(1, 11)]
        print(f"[Customer {customer_id}] Extracted {len(records)} records")
        return len(records)

    def load_customer_data(**context):
        dag_run = context["dag_run"]
        customer_id = dag_run.conf.get("customer_id")
        ti = context["ti"]

        record_count = ti.xcom_pull(task_ids="extract_data")
        print(f"[Customer {customer_id}] Loading {record_count} records to database")
        print(f"[Customer {customer_id}] Load complete")

    extract = PythonOperator(task_id="extract_data", python_callable=extract_customer_data)
    load = PythonOperator(task_id="load_data", python_callable=load_customer_data)

    extract >> load


# =============================================================================
# PARENT DAG: runs ETL for multiple customers, waits for each one
# =============================================================================
with DAG(
    dag_id="multi_customer_orchestrator",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["orchestrator", "wait", "example"],
) as orchestrator:

    def get_customers_to_process(**context):
        """Return list of customers that need processing today."""
        # In real life: SELECT customer_id FROM customers WHERE is_active = true
        customers = [
            {"id": 101, "region": "US"},
            {"id": 202, "region": "EU"},
            {"id": 303, "region": "APAC"},
        ]
        print(f"Found {len(customers)} customers to process")
        return customers

    get_customers = PythonOperator(
        task_id="get_customers",
        python_callable=get_customers_to_process,
    )

    # Trigger customer ETL — WAIT for completion before continuing
    # This creates a sequential chain: orchestrator waits for each customer
    trigger_customer_101 = TriggerDagRunOperator(
        task_id="trigger_etl_customer_101",
        trigger_dag_id="customer_etl_pipeline",
        conf={
            "customer_id": 101,
            "region": "US",
            "date": "{{ ds }}",
        },
        wait_for_completion=True,       # Block until child DAG finishes
        poke_interval=15,               # Check child status every 15 seconds
        allowed_states=["success"],     # Only succeed if child succeeds
        failed_states=["failed", "upstream_failed"],  # Fail if child fails
        reset_dag_run=True,
        execution_timeout=timedelta(hours=1),  # Don't wait more than 1 hour
    )

    trigger_customer_202 = TriggerDagRunOperator(
        task_id="trigger_etl_customer_202",
        trigger_dag_id="customer_etl_pipeline",
        conf={
            "customer_id": 202,
            "region": "EU",
            "date": "{{ ds }}",
        },
        wait_for_completion=True,
        poke_interval=15,
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        reset_dag_run=True,
    )

    trigger_customer_303 = TriggerDagRunOperator(
        task_id="trigger_etl_customer_303",
        trigger_dag_id="customer_etl_pipeline",
        conf={
            "customer_id": 303,
            "region": "APAC",
            "date": "{{ ds }}",
        },
        wait_for_completion=True,
        poke_interval=15,
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        reset_dag_run=True,
    )

    def send_completion_notification(**context):
        """All customer ETLs done — send a summary notification."""
        print(f"All customer ETL pipelines completed for {context['ds']}")
        print("Customers processed: 101 (US), 202 (EU), 303 (APAC)")
        # Send Slack, email, etc.

    notify = PythonOperator(
        task_id="send_completion_notification",
        python_callable=send_completion_notification,
    )

    # Run all three customers in parallel (they all trigger simultaneously)
    # Each trigger waits for its own child DAG to finish
    get_customers >> [trigger_customer_101, trigger_customer_202, trigger_customer_303] >> notify
```

**What to notice:**
- `schedule_interval=None` on child DAGs prevents them from running autonomously
- `wait_for_completion=True` makes the parent task block until the child DAG finishes — the parent holds a worker slot during this time
- `allowed_states` and `failed_states` control how parent reacts to child outcome
- `poke_interval` controls how often the parent checks the child's status (in seconds)
- `reset_dag_run=True` allows idempotent re-runs — if the child DAG already ran for that execution date, it resets and re-runs
- `conf` is the only way to pass data into a triggered DAG — access it via `context["dag_run"].conf`
- Running multiple triggers in parallel (`[trigger_1, trigger_2, trigger_3]`) means all three child DAGs start at the same time but each trigger task waits for its own child
