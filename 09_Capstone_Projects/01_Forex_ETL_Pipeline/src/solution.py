"""
forex_etl_pipeline_solution.py
================================
Project 01 — Forex ETL Pipeline (Beginner) — COMPLETE SOLUTION

Fetches live forex rates from exchangerate-api.com, transforms them,
loads to PostgreSQL, logs a summary email, and cleans up temp files.

Schedule: Daily at 06:00 UTC
Airflow 3 (airflow.sdk imports)

Prerequisites:
    pip install apache-airflow-providers-http apache-airflow-providers-postgres

    Airflow connections:
        forex_api      : HTTP, host=https://v6.exchangerate-api.com
        forex_postgres : Postgres, host=localhost, schema=forex, port=5432

    Environment variable:
        FOREX_API_KEY=your_key (free from exchangerate-api.com; "demo" works for testing)
"""

import json
import os
import csv
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.hooks.http import HttpHook
from airflow.sensors.filesystem import FileSensor
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_CURRENCY = "USD"
TARGET_CURRENCIES = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY"]
DATA_DIR = "/tmp/forex"
CONFIG_FILE = f"{DATA_DIR}/currencies.json"

# ── Default args ───────────────────────────────────────────────────────────────
default_args = {
    "owner": "data-team",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email_on_retry": False,
    "email": ["data-team@company.com"],
}

# ── DAG ────────────────────────────────────────────────────────────────────────
with DAG(
    dag_id="forex_etl_pipeline",
    description="Daily forex ETL: API → CSV → PostgreSQL → Email",
    start_date=datetime(2024, 1, 1),
    schedule="0 6 * * *",      # ← 6am UTC every day
    catchup=False,
    default_args=default_args,
    tags=["beginner", "etl", "forex"],
) as dag:

    # ── Task 1: Confirm the API responds ──────────────────────────────────────
    # HttpSensor polls /v6/latest/USD every 5 s until we get result == "success".
    # If the API is down, the sensor fails after 20 s rather than letting
    # the fetch task run and fail with a cryptic error.
    check_api_availability = HttpSensor(
        task_id="check_api_availability",
        http_conn_id="forex_api",
        endpoint="/v6/latest/USD",
        request_params={"apikey": os.environ.get("FOREX_API_KEY", "demo")},
        response_check=lambda response: response.json().get("result") == "success",
        poke_interval=5,
        timeout=20,
    )

    # ── Task 2: Confirm the config file exists ────────────────────────────────
    # mode="reschedule" returns the worker slot to the pool while waiting.
    # This matters when sensors could block for minutes — the pool slot
    # would be wasted otherwise.
    check_config_file = FileSensor(
        task_id="check_config_file",
        filepath=CONFIG_FILE,
        poke_interval=5,
        timeout=60,
        mode="reschedule",      # ← don't block a worker while waiting
    )

    # ── Task 3: Fetch rates from the API ──────────────────────────────────────
    def fetch_forex_rates(**context):
        """
        Read config, call the API via HttpHook, push rates to XCom.
        Using HttpHook (not requests.get) lets Airflow manage the connection
        config (host, timeout, headers) centrally.
        """
        # Read which currencies we want from the local config file
        with open(CONFIG_FILE) as f:
            config = json.load(f)

        base_currency = config.get("base", "USD")
        currencies = config.get("currencies", TARGET_CURRENCIES)

        # HttpHook uses the "forex_api" connection for host/auth details
        hook = HttpHook(method="GET", http_conn_id="forex_api")
        response = hook.run(
            endpoint=f"/v6/{os.environ.get('FOREX_API_KEY', 'demo')}/latest/{base_currency}",
        )
        data = response.json()

        if data.get("result") != "success":
            raise ValueError(f"API error: {data.get('error-type', 'unknown')}")

        # Filter to only the currencies in the config
        all_rates = data["conversion_rates"]
        selected_rates = {c: all_rates[c] for c in currencies if c in all_rates}

        print(f"Fetched {len(selected_rates)} rates for base: {base_currency}")

        # Push to XCom — downstream tasks pull with xcom_pull(key="rates")
        context["ti"].xcom_push(key="rates", value=selected_rates)
        context["ti"].xcom_push(key="base_currency", value=base_currency)
        return selected_rates

    fetch_rates = PythonOperator(
        task_id="fetch_forex_rates",
        python_callable=fetch_forex_rates,
    )

    # ── Task 4: Transform rates into a CSV file ───────────────────────────────
    def save_rates_to_csv(**context):
        """
        Pull rates from XCom, write one row per currency to a date-stamped CSV.
        Push the file path back to XCom so the loader and cleanup tasks know it.
        """
        execution_date = context["ds_nodash"]   # e.g. "20240115"

        rates = context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="rates")
        base_currency = context["ti"].xcom_pull(
            task_ids="fetch_forex_rates", key="base_currency"
        )

        if not rates:
            raise ValueError("No rates in XCom — did fetch_forex_rates succeed?")

        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        csv_path = f"{DATA_DIR}/forex_rates_{execution_date}.csv"

        with open(csv_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=["base_currency", "target_currency", "rate", "fetched_at"],
            )
            writer.writeheader()
            for target_currency, rate in rates.items():
                writer.writerow({
                    "base_currency": base_currency,
                    "target_currency": target_currency,
                    "rate": rate,
                    "fetched_at": context["ts"],    # ← Airflow task start timestamp
                })

        print(f"Wrote {len(rates)} rows to {csv_path}")
        context["ti"].xcom_push(key="csv_path", value=csv_path)
        return csv_path

    write_csv = PythonOperator(
        task_id="save_rates_to_csv",
        python_callable=save_rates_to_csv,
    )

    # ── Task 5: Create the target table if needed ─────────────────────────────
    # PostgresOperator runs SQL directly against the configured connection.
    # CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS = safe to run every day.
    create_forex_table = PostgresOperator(
        task_id="create_forex_table",
        postgres_conn_id="forex_postgres",
        sql="""
            CREATE TABLE IF NOT EXISTS forex_rates (
                id               SERIAL PRIMARY KEY,
                base_currency    VARCHAR(10)    NOT NULL,
                target_currency  VARCHAR(10)    NOT NULL,
                rate             NUMERIC(20, 8) NOT NULL,
                fetched_at       TIMESTAMP      NOT NULL,
                execution_date   DATE           NOT NULL DEFAULT '{{ ds }}'::DATE
            );

            CREATE INDEX IF NOT EXISTS idx_forex_rates_date
                ON forex_rates(execution_date);
        """,
    )

    # ── Task 6: Load CSV rows into Postgres ───────────────────────────────────
    def load_rates_to_postgres(**context):
        """
        Read the CSV and insert rows using a raw psycopg2 cursor.
        ON CONFLICT DO NOTHING makes re-runs safe — no duplicates created.
        """
        csv_path = context["ti"].xcom_pull(task_ids="save_rates_to_csv", key="csv_path")

        if not csv_path or not Path(csv_path).exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        hook = PostgresHook(postgres_conn_id="forex_postgres")
        conn = hook.get_conn()
        cursor = conn.cursor()
        rows_inserted = 0

        with open(csv_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                cursor.execute(
                    """
                    INSERT INTO forex_rates
                        (base_currency, target_currency, rate, fetched_at, execution_date)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        row["base_currency"],
                        row["target_currency"],
                        float(row["rate"]),
                        row["fetched_at"],
                        context["ds"],          # ← logical date of the DAG run
                    ),
                )
                rows_inserted += 1

        conn.commit()
        cursor.close()
        conn.close()

        print(f"Inserted {rows_inserted} rows into forex_rates for {context['ds']}")
        context["ti"].xcom_push(key="rows_inserted", value=rows_inserted)

    insert_rates = PythonOperator(
        task_id="load_rates_to_postgres",
        python_callable=load_rates_to_postgres,
    )

    # ── Task 7: Log a summary email ───────────────────────────────────────────
    def send_summary_email(**context):
        """
        Compose the stakeholder email from XCom data and print it.
        In production, replace the print with:
            from airflow.utils.email import send_email
            send_email(to="risk-team@company.com", subject=subject, html_content=body)
        """
        rates = context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="rates")
        base = context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="base_currency")
        rows = context["ti"].xcom_pull(task_ids="load_rates_to_postgres", key="rows_inserted")

        rate_lines = "\n".join(
            f"  {base}/{currency}: {rate:.4f}" for currency, rate in rates.items()
        )

        subject = f"Forex Rates Loaded — {context['ds']}"
        body = (
            f"Forex ETL pipeline completed successfully.\n\n"
            f"Date: {context['ds']}\n"
            f"Base currency: {base}\n"
            f"Rates loaded: {rows}\n\n"
            f"Exchange rates:\n{rate_lines}\n\n"
            f"Data available in PostgreSQL:\n"
            f"  SELECT * FROM forex_rates WHERE execution_date = '{context['ds']}';"
        )

        print("=" * 50)
        print(f"SUBJECT: {subject}")
        print("=" * 50)
        print(body)

    send_notification = PythonOperator(
        task_id="send_summary_email",
        python_callable=send_summary_email,
    )

    # ── Task 8: Delete the temp CSV ───────────────────────────────────────────
    # trigger_rule="all_done" ensures cleanup runs even if an upstream task failed,
    # so we never leave orphaned files on disk.
    cleanup = BashOperator(
        task_id="cleanup_csv",
        bash_command="rm -f {{ ti.xcom_pull(task_ids='save_rates_to_csv', key='csv_path') }}",
        trigger_rule="all_done",    # ← runs regardless of success or failure upstream
    )

    # ── Dependency chain ───────────────────────────────────────────────────────
    #
    # check_api_availability ──┐
    #                           ├──► fetch_rates ──► write_csv ──► create_table
    # check_config_file ────────┘                                       │
    #                                                                    ▼
    #                                                              insert_rates
    #                                                                    │
    #                                                                    ▼
    #                                                           send_notification
    #                                                                    │
    #                                                                    ▼
    #                                                               cleanup
    #
    [check_api_availability, check_config_file] >> fetch_rates
    fetch_rates >> write_csv >> create_forex_table >> insert_rates >> send_notification >> cleanup
