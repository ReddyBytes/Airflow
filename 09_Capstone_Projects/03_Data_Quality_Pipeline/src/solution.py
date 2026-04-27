"""
data_quality_pipeline_solution.py
====================================
Project 03 — Data Quality Gate Pipeline (Intermediate) — COMPLETE SOLUTION

Extract from Postgres staging → Great Expectations validation →
warehouse load (pass) or email alert (fail).

Required:
    pip install apache-airflow-providers-postgres \
                great-expectations \
                apache-airflow-providers-great-expectations

    Airflow connections:
        postgres_staging   : Postgres staging DB
        postgres_warehouse : Postgres warehouse DB

    GX resources (see 03_GUIDE.md Step 2–3 to create):
        Expectation suite : orders_quality_suite
        Checkpoint        : orders_checkpoint
        Data Context      : /opt/airflow/great_expectations
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

# ── Default args ──────────────────────────────────────────────────────────────
default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": ALERT_EMAIL,
}


# ── Callables ─────────────────────────────────────────────────────────────────

def check_staging_data(**context) -> None:
    """
    Verify staging.orders has rows for the logical date.
    Fail fast if not — better to know immediately than to run a GX checkpoint
    on empty data and get a confusing result.
    """
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=STAGING_CONN)

    count = hook.get_first(
        "SELECT COUNT(*) FROM staging.orders WHERE order_date = %s",
        parameters=[ds],
    )[0]

    print(f"[check_staging] {count} rows found for {ds}")

    if count == 0:
        raise ValueError(
            f"No staging data for {ds}. Check upstream ingestion pipeline."
        )

    context["ti"].xcom_push(key="staging_row_count", value=count)


def branch_on_validation_result(**context) -> str:
    """
    Read the GX result from XCom and route to the correct downstream path.

    GreatExpectationsOperator with return_json_dict=True stores the full
    result dict as the task's return_value in XCom.
    """
    # xcom_pull without key= returns the task's return_value
    result = context["ti"].xcom_pull(task_ids="validate_data")

    if result is None:
        print("[branch] No validation result in XCom — treating as failure")
        return "build_failure_report"

    success = result.get("success", False)
    stats = result.get("statistics", {})
    evaluated = stats.get("evaluated_expectations", 0)
    failed = stats.get("unsuccessful_expectations", 0)

    print(
        f"[branch] Validation {'PASSED' if success else 'FAILED'}. "
        f"Evaluated: {evaluated}, Failed: {failed}"
    )

    return "load_to_warehouse" if success else "build_failure_report"


def load_validated_rows(**context) -> None:
    """
    INSERT validated rows from staging into the warehouse.
    Idempotent: ON CONFLICT (order_id) DO UPDATE means re-runs are safe.
    """
    ds = context["ds"]
    hook = PostgresHook(postgres_conn_id=WAREHOUSE_CONN)

    # Only move rows that pass our business rules
    # (GX validated the suite; this WHERE clause mirrors the strictest expectations)
    hook.run(
        """
        INSERT INTO warehouse.orders
            (order_id, customer_id, amount, currency, status, order_date)
        SELECT
            order_id, customer_id, amount, currency, status, order_date
        FROM staging.orders
        WHERE order_date    = %(ds)s
          AND customer_id   IS NOT NULL
          AND amount        >= 0.01
          AND status        IN ('pending','shipped','delivered','cancelled','refunded')
        ON CONFLICT (order_id) DO UPDATE
            SET amount    = EXCLUDED.amount,
                status    = EXCLUDED.status,
                loaded_at = NOW()
        """,
        parameters={"ds": ds},
    )

    # Verify final count in warehouse
    wh_count = hook.get_first(
        "SELECT COUNT(*) FROM warehouse.orders WHERE order_date = %s",
        parameters=[ds],
    )[0]

    print(f"[load] Warehouse contains {wh_count} rows for {ds}")
    context["ti"].xcom_push(key="warehouse_row_count", value=wh_count)


def build_failure_report(**context) -> str:
    """
    Summarise which GX expectations failed.
    The summary is stored in XCom so the EmailOperator can include it via Jinja.
    """
    ds = context["ds"]
    result = context["ti"].xcom_pull(task_ids="validate_data") or {}
    stats = result.get("statistics", {})

    # Find expectations that failed
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
    ]

    report = "\n".join(lines)
    print(report)
    context["ti"].xcom_push(key="failure_report", value=report)
    return report


# ── DAG ───────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="data_quality_pipeline",
    description="Postgres staging → GX validation → warehouse load or alert",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    tags=["intermediate", "data-quality", "great-expectations"],
) as dag:

    # ── Task 1: Fail fast if no staging data ─────────────────────────────────
    check_staging = PythonOperator(
        task_id="check_staging",
        python_callable=check_staging_data,
    )

    # ── Task 2: Run GX checkpoint ─────────────────────────────────────────────
    # fail_task_on_validation_failure=False keeps the task green on GX failure
    # so that downstream tasks (especially the alert) still execute.
    # return_json_dict=True pushes the full result dict to XCom.
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
        fail_task_on_validation_failure=False,  # ← we route manually
        return_json_dict=True,                  # ← push result to XCom
    )

    # ── Task 3: Route on pass/fail ────────────────────────────────────────────
    branch = BranchPythonOperator(
        task_id="branch_on_quality",
        python_callable=branch_on_validation_result,
    )

    # ── Task 4a: Load clean rows to warehouse ─────────────────────────────────
    load = PythonOperator(
        task_id="load_to_warehouse",
        python_callable=load_validated_rows,
    )

    # ── Task 4b: Build failure summary ────────────────────────────────────────
    build_report = PythonOperator(
        task_id="build_failure_report",
        python_callable=build_failure_report,
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
        <pre>{{ task_instance.xcom_pull(task_ids='build_failure_report',
                                        key='failure_report') }}</pre>
        <p><a href="http://airflow-webserver:8080">View in Airflow UI</a></p>
        """,
    )

    # ── Task 5: Convergence marker ────────────────────────────────────────────
    # EmptyOperator does nothing — it's a clean terminal point.
    # trigger_rule lets it run after either branch completes.
    done = EmptyOperator(
        task_id="pipeline_complete",
        trigger_rule="none_failed_min_one_success",
    )

    # ── Dependency chain ───────────────────────────────────────────────────────
    #
    # check_staging → validate → branch ─┬─ load ──────────────────────────┐
    #                                     │                                  ├─ done
    #                                     └─ build_report → alert ──────────┘
    #
    check_staging >> validate >> branch
    branch >> load >> done
    branch >> build_report >> alert >> done
