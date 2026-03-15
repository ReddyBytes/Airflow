# 🟢 Forex ETL Pipeline — Complete DAG Code

Complete, well-commented Airflow 3 DAG. Copy to your `dags/` directory.

```python
"""
forex_etl_pipeline.py
=====================
Project 01 — Forex ETL Pipeline (Beginner)

Fetches live forex exchange rates from exchangerate-api.com,
transforms them, loads to PostgreSQL, and sends an email summary.

Schedule: Daily at 06:00 UTC
Airflow 3 syntax (uses airflow.sdk imports)

Prerequisites:
  pip install apache-airflow-providers-http apache-airflow-providers-postgres

  Airflow connections needed:
    - forex_api:       HTTP, host=https://v6.exchangerate-api.com
    - forex_postgres:  Postgres, host=localhost, schema=forex, port=5432

  Environment variable:
    FOREX_API_KEY=your_api_key_here
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

# ── Constants ────────────────────────────────────────────────────
BASE_CURRENCY = "USD"
TARGET_CURRENCIES = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY"]
DATA_DIR = "/tmp/forex"
CONFIG_FILE = f"{DATA_DIR}/currencies.json"
RATES_CSV = f"{DATA_DIR}/forex_rates_{{{{ ds_nodash }}}}.csv"

# ── Default args applied to all tasks ────────────────────────────
default_args = {
    "owner": "data-team",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email_on_retry": False,
    "email": ["data-team@company.com"],
}

# ── DAG definition ───────────────────────────────────────────────
with DAG(
    dag_id="forex_etl_pipeline",
    description="Daily forex ETL: API → PostgreSQL → Email",
    start_date=datetime(2024, 1, 1),
    schedule="0 6 * * *",          # Run at 6:00 AM UTC daily
    catchup=False,
    default_args=default_args,
    tags=["beginner", "etl", "forex"],
    doc_md="""
    ## Forex ETL Pipeline

    Fetches daily forex rates from exchangerate-api.com and loads them to PostgreSQL.

    | Step | Operator | Description |
    |------|----------|-------------|
    | 1 | HttpSensor | Wait for API to respond |
    | 2 | FileSensor | Wait for currencies config file |
    | 3 | PythonOperator | Fetch rates from API |
    | 4 | PythonOperator | Transform and write to CSV |
    | 5 | PostgresOperator | Create table if not exists |
    | 6 | PostgresOperator | Insert today's rates |
    | 7 | PythonOperator | Send summary email |
    """,
) as dag:

    # ── Task 1: Check that the forex API is available ─────────────
    # HttpSensor polls the endpoint until it gets a 200 response
    # poke_interval: check every 5 seconds
    # timeout: give up after 20 seconds
    check_api_availability = HttpSensor(
        task_id="check_api_availability",
        http_conn_id="forex_api",
        endpoint="/v6/latest/USD",
        request_params={"apikey": os.environ.get("FOREX_API_KEY", "demo")},
        response_check=lambda response: response.json().get("result") == "success",
        poke_interval=5,
        timeout=20,
    )

    # ── Task 2: Check that the currencies config file exists ──────
    # FileSensor waits for the config file to appear
    # mode="reschedule": releases the worker slot while waiting
    check_config_file = FileSensor(
        task_id="check_config_file",
        filepath=CONFIG_FILE,
        poke_interval=5,
        timeout=60,
        mode="reschedule",          # Don't block a worker slot while waiting
    )

    # ── Task 3: Fetch forex rates from the API ────────────────────
    def fetch_forex_rates(**context):
        """
        Fetch exchange rates from the API and push to XCom.
        The next task will read these rates and write them to CSV.
        """
        # Read which currencies we want from the config file
        with open(CONFIG_FILE) as f:
            config = json.load(f)

        base_currency = config.get("base", "USD")
        currencies = config.get("currencies", TARGET_CURRENCIES)

        # Call the API using the Airflow HTTP hook
        # This respects the connection we set up (host, timeout, auth)
        hook = HttpHook(method="GET", http_conn_id="forex_api")
        response = hook.run(
            endpoint=f"/v6/{os.environ.get('FOREX_API_KEY', 'demo')}/latest/{base_currency}",
        )
        data = response.json()

        if data.get("result") != "success":
            raise ValueError(f"API returned error: {data.get('error-type', 'unknown')}")

        # Extract only the rates we care about
        all_rates = data["conversion_rates"]
        selected_rates = {
            currency: all_rates[currency]
            for currency in currencies
            if currency in all_rates
        }

        print(f"Fetched {len(selected_rates)} rates for base currency: {base_currency}")

        # Push rates to XCom so the next task can use them
        # XCom key is "rates" — we'll pull with xcom_pull(key="rates")
        context["ti"].xcom_push(key="rates", value=selected_rates)
        context["ti"].xcom_push(key="base_currency", value=base_currency)

        return selected_rates

    fetch_rates = PythonOperator(
        task_id="fetch_forex_rates",
        python_callable=fetch_forex_rates,
    )

    # ── Task 4: Transform rates and write to CSV ──────────────────
    def save_rates_to_csv(**context):
        """
        Read rates from XCom and write to a CSV file.
        The CSV will be used by the PostgresOperator for loading.
        """
        execution_date = context["ds_nodash"]

        # Pull the rates that the previous task fetched
        rates = context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="rates")
        base_currency = context["ti"].xcom_pull(
            task_ids="fetch_forex_rates", key="base_currency"
        )

        if not rates:
            raise ValueError("No rates found in XCom — did fetch_forex_rates succeed?")

        # Create output directory if it doesn't exist
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

        # Write to CSV
        csv_path = f"{DATA_DIR}/forex_rates_{execution_date}.csv"
        rows_written = 0

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
                    "fetched_at": context["ts"],   # Airflow task start timestamp
                })
                rows_written += 1

        print(f"Wrote {rows_written} rates to {csv_path}")

        # Push CSV path for the Postgres task
        context["ti"].xcom_push(key="csv_path", value=csv_path)
        return csv_path

    write_csv = PythonOperator(
        task_id="save_rates_to_csv",
        python_callable=save_rates_to_csv,
    )

    # ── Task 5: Create the target table if it doesn't exist ───────
    # PostgresOperator runs SQL against the configured Postgres connection
    # The {{ ds }} template is replaced with the execution date at runtime
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

            -- Add an index on date for faster lookups
            CREATE INDEX IF NOT EXISTS idx_forex_rates_date
                ON forex_rates(execution_date);
        """,
    )

    # ── Task 6: Load the CSV data into PostgreSQL ─────────────────
    def load_rates_to_postgres(**context):
        """
        Read the CSV written by the previous task and insert rows into Postgres.
        Uses PostgresHook for direct database access.
        """
        csv_path = context["ti"].xcom_pull(task_ids="save_rates_to_csv", key="csv_path")

        if not csv_path or not Path(csv_path).exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

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
                        context["ds"],
                    ),
                )
                rows_inserted += 1

        conn.commit()
        cursor.close()
        conn.close()

        print(f"Inserted {rows_inserted} rows into forex_rates table")
        context["ti"].xcom_push(key="rows_inserted", value=rows_inserted)

    insert_rates = PythonOperator(
        task_id="load_rates_to_postgres",
        python_callable=load_rates_to_postgres,
    )

    # ── Task 7: Send a summary email to the risk team ─────────────
    def send_summary_email(**context):
        """
        Compose and send a summary email with the day's exchange rates.
        In production, use airflow.utils.email.send_email for real email.
        """
        rates = context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="rates")
        base = context["ti"].xcom_pull(task_ids="fetch_forex_rates", key="base_currency")
        rows = context["ti"].xcom_pull(task_ids="load_rates_to_postgres", key="rows_inserted")

        # Build the email body
        rate_lines = "\n".join(
            f"  {base}/{currency}: {rate:.4f}" for currency, rate in rates.items()
        )

        email_body = f"""
Forex ETL pipeline completed successfully.

Date: {context['ds']}
Base currency: {base}
Rates loaded: {rows}

Exchange rates:
{rate_lines}

Data is available in PostgreSQL:
  SELECT * FROM forex_rates WHERE execution_date = '{context['ds']}';
        """.strip()

        # In production, use send_email:
        # from airflow.utils.email import send_email
        # send_email(
        #     to="risk-team@company.com",
        #     subject=f"Forex Rates Loaded — {context['ds']}",
        #     html_content=email_body,
        # )

        # For now, log the email content
        print("=" * 50)
        print(f"SUBJECT: Forex Rates Loaded — {context['ds']}")
        print("=" * 50)
        print(email_body)

    send_notification = PythonOperator(
        task_id="send_summary_email",
        python_callable=send_summary_email,
    )

    # ── Task 8: Clean up the temp CSV file ────────────────────────
    cleanup = BashOperator(
        task_id="cleanup_csv",
        bash_command="rm -f {{ ti.xcom_pull(task_ids='save_rates_to_csv', key='csv_path') }}",
        trigger_rule="all_done",    # Run even if a task fails
    )

    # ── Task dependencies ─────────────────────────────────────────
    #
    # check_api_availability ─┐
    #                          ├─► fetch_rates ─► write_csv ─► create_table ─► insert ─► email ─► cleanup
    # check_config_file ──────┘
    #
    [check_api_availability, check_config_file] >> fetch_rates
    fetch_rates >> write_csv >> create_forex_table >> insert_rates >> send_notification >> cleanup
```

---

## How to Run

```bash
# 1. Copy DAG to your dags folder
cp forex_etl_pipeline.py ~/airflow/dags/

# 2. Set your API key as an environment variable
export FOREX_API_KEY=your_api_key_here

# 3. Create the currencies config
mkdir -p /tmp/forex
echo '{"base": "USD", "currencies": ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY"]}' \
  > /tmp/forex/currencies.json

# 4. Trigger a test run
airflow dags trigger forex_etl_pipeline

# 5. Watch the logs
airflow tasks logs forex_etl_pipeline fetch_forex_rates $(date +%Y-%m-%d)

# 6. Check the database
psql -U airflow -d forex -c "SELECT * FROM forex_rates ORDER BY fetched_at DESC LIMIT 10;"
```

---

## Testing Individual Tasks

```bash
# Test each task individually without running the full DAG
airflow tasks test forex_etl_pipeline check_api_availability 2024-01-15
airflow tasks test forex_etl_pipeline fetch_forex_rates 2024-01-15
airflow tasks test forex_etl_pipeline save_rates_to_csv 2024-01-15
airflow tasks test forex_etl_pipeline create_forex_table 2024-01-15
airflow tasks test forex_etl_pipeline load_rates_to_postgres 2024-01-15
```
