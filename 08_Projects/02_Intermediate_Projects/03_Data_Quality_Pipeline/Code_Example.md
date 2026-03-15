# Data Quality Pipeline — Full DAG Code

Complete, production-ready DAG implementing the extract → validate → branch → load
or alert pattern. Copy this into `dags/data_quality_pipeline.py`.

---

```python
"""
data_quality_pipeline.py
========================
Pipeline: Postgres staging → Great Expectations validation → warehouse load or alert.

Required Airflow connections:
  - postgres_staging   : Postgres staging database
  - postgres_warehouse : Postgres warehouse database

Required GX resources:
  - Expectation suite : orders_quality_suite
  - Checkpoint        : orders_checkpoint
  - Data Context      : /opt/airflow/great_expectations
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.email import EmailOperator
from airflow.operators.empty import EmptyOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator

# ── Constants ─────────────────────────────────────────────────────────────────
GX_ROOT = "/opt/airflow/great_expectations"
STAGING_CONN = "postgres_staging"
WAREHOUSE_CONN = "postgres_warehouse"
ALERT_EMAIL = "data-team@company.com"


# ── Callables ─────────────────────────────────────────────────────────────────

def check_staging_data(**context) -> None:
    """Verify that staging rows exist for the logical date. Fail fast if not."""
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=STAGING_CONN)

    count = hook.get_first(
        "SELECT COUNT(*) FROM staging.orders WHERE order_date = %s",
        parameters=[ds],
    )[0]

    print(f"[check_staging_data] {count} rows found for {ds}")

    if count == 0:
        raise ValueError(
            f"No staging data for {ds}. Check upstream ingestion pipeline."
        )

    context["ti"].xcom_push(key="staging_row_count", value=count)


def branch_on_validation_result(**context) -> str:
    """
    Read GX validation result from XCom.
    Route to load task on success, alert task on failure.
    """
    result = context["ti"].xcom_pull(task_ids="validate_data")

    if result is None:
        print("[branch] No validation result in XCom — treating as failure.")
        return "send_failure_alert"

    success = result.get("success", False)
    stats = result.get("statistics", {})
    evaluated = stats.get("evaluated_expectations", 0)
    failed = stats.get("unsuccessful_expectations", 0)

    print(
        f"[branch] Validation {'PASSED' if success else 'FAILED'}. "
        f"Evaluated: {evaluated}, Failed: {failed}"
    )

    return "load_to_warehouse" if success else "send_failure_alert"


def load_validated_rows(**context) -> None:
    """
    Insert validated rows from staging into the warehouse.
    Uses INSERT ... ON CONFLICT to be idempotent.
    """
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)

    sql = """
        INSERT INTO warehouse.orders
            (order_id, customer_id, amount, currency, status, order_date)
        SELECT
            order_id,
            customer_id,
            amount,
            currency,
            status,
            order_date
        FROM staging.orders
        WHERE order_date    = %(ds)s
          AND customer_id   IS NOT NULL
          AND amount        >= 0.01
          AND status        IN ('pending','shipped','delivered','cancelled','refunded')
        ON CONFLICT (order_id) DO UPDATE
            SET amount    = EXCLUDED.amount,
                status    = EXCLUDED.status,
                loaded_at = NOW()
    """

    hook.run(sql, parameters={"ds": ds})

    # Verify row count in warehouse
    wh_count = hook.get_first(
        "SELECT COUNT(*) FROM warehouse.orders WHERE order_date = %s",
        parameters=[ds],
    )[0]

    print(f"[load] Warehouse now contains {wh_count} rows for {ds}")
    context["ti"].xcom_push(key="warehouse_row_count", value=wh_count)


def build_failure_report(**context) -> str:
    """Build a plain-text failure summary for the alert email."""
    ds = context["ds"]
    result = context["ti"].xcom_pull(task_ids="validate_data") or {}
    stats = result.get("statistics", {})
    failed_expectations = [
        r for r in result.get("results", []) if not r.get("success", True)
    ]

    lines = [
        f"Data quality validation FAILED for date: {ds}",
        "",
        f"Evaluated expectations : {stats.get('evaluated_expectations', 'N/A')}",
        f"Failed expectations    : {stats.get('unsuccessful_expectations', 'N/A')}",
        "",
        "Failed checks:",
    ]
    for r in failed_expectations:
        exp_type = r.get("expectation_config", {}).get("expectation_type", "unknown")
        col = r.get("expectation_config", {}).get("kwargs", {}).get("column", "table-level")
        lines.append(f"  - {exp_type} (column: {col})")

    lines += [
        "",
        "Action required: investigate staging.orders and re-run pipeline after fix.",
        "View Data Docs: http://airflow-webserver:8080/data-docs/",
    ]

    report = "\n".join(lines)
    print(report)
    context["ti"].xcom_push(key="failure_report", value=report)
    return report


# ── DAG ───────────────────────────────────────────────────────────────────────

default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": ALERT_EMAIL,
}

with DAG(
    dag_id="data_quality_pipeline",
    description="Extract from Postgres staging → GX validation → warehouse load or alert",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    tags=["intermediate", "data-quality", "great-expectations"],
    doc_md="""
    ## Data Quality Pipeline

    Validates daily order data from the staging database before loading to the
    warehouse. Any validation failure triggers an email alert instead of loading.

    **GX suite**: `orders_quality_suite`
    **Checkpoint**: `orders_checkpoint`
    """,
) as dag:

    # ── Task 1: Confirm staging data exists ───────────────────────────────────
    check_staging = PythonOperator(
        task_id="check_staging",
        python_callable=check_staging_data,
        doc_md="Verify staging.orders has rows for {{ ds }}. Fail fast if empty.",
    )

    # ── Task 2: Great Expectations validation ─────────────────────────────────
    validate = GreatExpectationsOperator(
        task_id="validate_data",
        checkpoint_name="orders_checkpoint",
        data_context_root_dir=GX_ROOT,
        checkpoint_kwargs={
            "batch_request": {
                "datasource_name": "postgres_staging",
                "data_connector_name": "default_inferred",
                "data_asset_name": "staging.orders",
            }
        },
        fail_task_on_validation_failure=False,  # we branch manually
        return_json_dict=True,                  # push result dict to XCom
        doc_md="Run GX checkpoint against today's staging data.",
    )

    # ── Task 3: Branch on result ──────────────────────────────────────────────
    branch = BranchPythonOperator(
        task_id="branch_on_quality",
        python_callable=branch_on_validation_result,
        doc_md="Route to load if validation passed, else alert.",
    )

    # ── Task 4a: Load clean rows to warehouse ─────────────────────────────────
    load = PythonOperator(
        task_id="load_to_warehouse",
        python_callable=load_validated_rows,
        doc_md="INSERT validated rows into warehouse.orders (idempotent).",
    )

    # ── Task 4b: Build failure report ─────────────────────────────────────────
    build_report = PythonOperator(
        task_id="build_failure_report",
        python_callable=build_failure_report,
        doc_md="Summarise which expectations failed.",
    )

    # ── Task 4c: Send email alert ─────────────────────────────────────────────
    alert = EmailOperator(
        task_id="send_failure_alert",
        to=ALERT_EMAIL,
        subject="[AIRFLOW] Data Quality FAILED — {{ ds }}",
        html_content="""
        <h2>Data Quality Validation Failed</h2>
        <p><strong>Date:</strong> {{ ds }}</p>
        <p><strong>DAG:</strong> data_quality_pipeline</p>
        <p>
            {{ task_instance.xcom_pull(task_ids='build_failure_report',
                                       key='failure_report') | replace('\\n', '<br>') }}
        </p>
        <p><a href="http://airflow-webserver:8080">View in Airflow UI</a></p>
        """,
        doc_md="Email the data team with validation failure details.",
    )

    # ── Task 5: Converge (runs regardless of branch) ─────────────────────────
    done = EmptyOperator(
        task_id="pipeline_complete",
        trigger_rule="none_failed_min_one_success",
        doc_md="Converge point — marks overall pipeline completion.",
    )

    # ── Dependencies ──────────────────────────────────────────────────────────
    check_staging >> validate >> branch
    branch >> load >> done
    branch >> build_report >> alert >> done
```

---

## Running the Pipeline

```bash
# Trigger for a specific date
airflow dags trigger data_quality_pipeline --exec-date 2024-01-15

# Backfill (if catchup=True)
airflow dags backfill data_quality_pipeline \
  --start-date 2024-01-01 --end-date 2024-01-31
```

---

## Testing the Failure Path

Insert bad data into staging:
```sql
INSERT INTO staging.orders VALUES
  ('ORD-BAD-001', NULL, 100.00, 'USD', 'shipped', '2024-01-16', NOW());
```

Trigger for `2024-01-16` → validation fails → email sent → warehouse NOT loaded.

---

## 📂 Navigation

| | |
|---|---|
| **Project Guide** | [Project_Guide.md](./Project_Guide.md) |
| **Step-by-Step** | [Step_by_Step.md](./Step_by_Step.md) |
| **Parent: Intermediate Projects** | [02_Intermediate_Projects](../Readme.md) |
| **Next: Multi-Source ETL** | [04_Multi_Source_ETL](../04_Multi_Source_ETL/Project_Guide.md) |
