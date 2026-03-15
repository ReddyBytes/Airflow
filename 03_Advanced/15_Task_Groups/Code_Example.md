# 15 — Task Groups: Code Examples

---

## Example 1: ETL DAG Organized into Three Task Groups

A realistic pipeline that extracts from two sources, validates and transforms data, then loads to staging and production with a notification step.

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
from datetime import datetime
import logging

# --- Callables ---

def pull_from_crm(**context):
    logging.info("Pulling data from CRM API")
    # Simulate extraction
    return {"rows": 1500, "source": "crm"}

def pull_from_warehouse(**context):
    logging.info("Pulling data from data warehouse")
    return {"rows": 3200, "source": "warehouse"}

def validate_schema(**context):
    logging.info("Validating column schema and data types")

def check_nulls(**context):
    logging.info("Checking for unexpected nulls in critical columns")

def normalize_dates(**context):
    logging.info("Normalizing date formats to ISO 8601")

def join_sources(**context):
    logging.info("Joining CRM and warehouse records on customer_id")

def calculate_metrics(**context):
    logging.info("Computing revenue, churn rate, and LTV metrics")

def write_to_staging(**context):
    logging.info("Writing transformed data to staging schema")

def write_to_production(**context):
    logging.info("Promoting staging data to production schema")

def send_success_notification(**context):
    logical_date = context["logical_date"]
    logging.info(f"Pipeline complete for {logical_date}. Notifying team.")


# --- DAG Definition ---

with DAG(
    dag_id="etl_with_task_groups",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example", "task_groups"],
) as dag:

    # ── Group 1: Extract ────────────────────────────────────────────────
    with TaskGroup("01_extract") as extract:
        pull_crm = PythonOperator(
            task_id="pull_crm",
            python_callable=pull_from_crm,
        )
        pull_wh = PythonOperator(
            task_id="pull_warehouse",
            python_callable=pull_from_warehouse,
        )
        # Both extractions run in parallel (no dependency between them)

    # ── Group 2: Transform ──────────────────────────────────────────────
    with TaskGroup("02_transform") as transform:
        with TaskGroup("validate") as validate:
            check_schema = PythonOperator(
                task_id="check_schema",
                python_callable=validate_schema,
            )
            check_null = PythonOperator(
                task_id="check_nulls",
                python_callable=check_nulls,
            )
            check_schema >> check_null

        with TaskGroup("process") as process:
            normalize = PythonOperator(
                task_id="normalize_dates",
                python_callable=normalize_dates,
            )
            join = PythonOperator(
                task_id="join_sources",
                python_callable=join_sources,
            )
            metrics = PythonOperator(
                task_id="calculate_metrics",
                python_callable=calculate_metrics,
            )
            normalize >> join >> metrics

        validate >> process

    # ── Group 3: Load ───────────────────────────────────────────────────
    with TaskGroup("03_load") as load:
        write_staging = PythonOperator(
            task_id="write_staging",
            python_callable=write_to_staging,
        )
        write_prod = PythonOperator(
            task_id="write_production",
            python_callable=write_to_production,
        )
        notify = PythonOperator(
            task_id="notify_success",
            python_callable=send_success_notification,
        )
        write_staging >> write_prod >> notify

    # ── Top-level pipeline flow ─────────────────────────────────────────
    extract >> transform >> load
```

**Result in the UI:**
```
[01_extract] ──► [02_transform] ──► [03_load]
```
Expand `02_transform` and you see two nested groups: `validate` and `process`.

---

## Example 2: Nested Task Groups with an Error Handling Group

A pipeline that processes multiple data sources in parallel, with a dedicated error handling group that runs when any processing task fails.

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule
from datetime import datetime
import logging


def extract_source(source: str, **context):
    logging.info(f"Extracting from {source}")

def process_source(source: str, **context):
    logging.info(f"Processing {source} data")

def merge_all(**context):
    logging.info("Merging all processed sources into final dataset")

def log_error_details(**context):
    exception = context.get("exception")
    logging.error(f"A processing task failed. Exception: {exception}")

def notify_on_call(**context):
    logging.error("Paging on-call engineer via PagerDuty")

def quarantine_bad_data(**context):
    logging.info("Moving failed-source data to quarantine bucket")

def cleanup_temp_files(**context):
    logging.info("Removing temporary files regardless of outcome")


def make_source_group(source_name: str) -> TaskGroup:
    """Factory function that creates a standardized source processing group."""
    with TaskGroup(f"source_{source_name}") as group:
        extract = PythonOperator(
            task_id="extract",
            python_callable=extract_source,
            op_kwargs={"source": source_name},
        )
        process = PythonOperator(
            task_id="process",
            python_callable=process_source,
            op_kwargs={"source": source_name},
        )
        extract >> process
    return group


with DAG(
    dag_id="nested_groups_with_error_handling",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example", "task_groups", "error_handling"],
) as dag:

    # ── Parallel source processing groups ───────────────────────────────
    crm_group  = make_source_group("crm")
    erp_group  = make_source_group("erp")
    api_group  = make_source_group("api")

    # ── Merge step ──────────────────────────────────────────────────────
    merge = PythonOperator(
        task_id="merge_all_sources",
        python_callable=merge_all,
    )

    # ── Error handling group — runs if ANY source group fails ───────────
    with TaskGroup("error_handling") as error_handling:
        log_error = PythonOperator(
            task_id="log_error_details",
            python_callable=log_error_details,
            trigger_rule=TriggerRule.ONE_FAILED,
        )
        notify = PythonOperator(
            task_id="notify_on_call",
            python_callable=notify_on_call,
        )
        quarantine = PythonOperator(
            task_id="quarantine_bad_data",
            python_callable=quarantine_bad_data,
        )
        log_error >> [notify, quarantine]

    # ── Cleanup — always runs ────────────────────────────────────────────
    cleanup = PythonOperator(
        task_id="cleanup_temp_files",
        python_callable=cleanup_temp_files,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # ── Wire up dependencies ─────────────────────────────────────────────
    [crm_group, erp_group, api_group] >> merge
    [crm_group, erp_group, api_group] >> error_handling
    merge >> cleanup
    error_handling >> cleanup
```

**Key points in this example:**
- `make_source_group()` is a factory function — call it once per source to generate a consistent group structure. Task IDs will be `source_crm.extract`, `source_crm.process`, etc.
- The `error_handling` group uses `TriggerRule.ONE_FAILED` on its entry task — it only activates when something goes wrong.
- The `cleanup` task uses `TriggerRule.ALL_DONE` — it runs regardless of whether the pipeline succeeded or failed.

---

## Navigation

**Prev:** [14 — Branching and Control Flow](../14_Branching_and_Control_Flow/Code_Example.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [16 — Dynamic Task Mapping](../16_Dynamic_Task_Mapping/Code_Example.md)
