# Project 01 — Step by Step Guide

Build the Forex ETL pipeline in 5 phases. Complete each phase and verify it works before moving to the next.

---

## Phase 1: Set Up Connections

Before writing any DAG code, configure the three connections that your tasks will use.

**In Airflow UI → Admin → Connections:**

### Forex API Connection

Click **+**, then fill in:
```
Conn Id:    forex_api
Conn Type:  HTTP
Host:       gist.githubusercontent.com
Schema:     https
Port:       443
```
Save.

### File Path Connection

Click **+**, then fill in:
```
Conn Id:    forex_path
Conn Type:  File (path)
Extra:      {"path": "/opt/airflow/files"}
```
Save.

### PostgreSQL Connection

Click **+**, then fill in:
```
Conn Id:    postgres_default
Conn Type:  Postgres
Host:       postgres
Schema:     airflow
Login:      airflow
Password:   airflow
Port:       5432
```
Save.

**Verify:** Test each connection by clicking the **Test** button. All three should show "Connection successfully tested."

---

## Phase 2: Build the Sensors

Sensors are tasks that wait for a condition to be true before proceeding. Create `forex_pipeline.py` in your `dags/` folder.

Start with the DAG skeleton and the two sensors:

```python
from airflow import DAG
from airflow.providers.http.sensors.http import HttpSensor
from airflow.sensors.filesystem import FileSensor
from datetime import datetime, timedelta

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "email": ["your_email@example.com"],
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="forex_etl_pipeline",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["forex", "etl", "project"],
) as dag:

    # Task 1: Check if the forex API is returning data
    check_forex_rates_available = HttpSensor(
        task_id="check_forex_rates_available",
        http_conn_id="forex_api",
        endpoint="ReddyBytes/Airflow/blob/main/forex_datapipeline/api-forex-exchange.json",
        method="GET",
        response_check=lambda response: "rates" in response.text,
        poke_interval=5,       # Check every 5 seconds
        timeout=20,            # Fail after 20 seconds if not available
    )

    # Task 2: Check if the local currency config file exists
    check_rates_file_available = FileSensor(
        task_id="check_rates_file_available",
        fs_conn_id="forex_path",
        filepath="forex_currencies.json",
        poke_interval=5,
        timeout=20,
    )
```

**Test this phase:**
```bash
# In the Airflow scheduler container
airflow tasks test forex_etl_pipeline check_forex_rates_available 2024-01-01
airflow tasks test forex_etl_pipeline check_rates_file_available 2024-01-01
```

---

## Phase 3: Build the Download Task

Add the function and task that fetches data from the forex API and saves it locally.

```python
import json
import requests
from airflow.operators.python import PythonOperator

def download_forex_rates():
    """
    Fetch forex exchange rates from the API.
    Read the currencies list from the local config file.
    Save the raw response to a JSON file.
    """
    import os

    # Load the list of currencies we want to track
    with open("/opt/airflow/files/forex_currencies.json") as f:
        config = json.load(f)

    base_currency = config["base"]
    target_currencies = config["currencies"]

    # Fetch rates from the API
    # Using a free open exchange rates API (no key needed for demo)
    url = f"https://open.er-api.com/v6/latest/{base_currency}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    data = response.json()

    # Filter to only the currencies we care about
    filtered_rates = {
        "base": base_currency,
        "date": data.get("time_last_update_utc", ""),
        "rates": {
            currency: data["rates"][currency]
            for currency in target_currencies
            if currency in data["rates"]
        }
    }

    # Save raw data
    os.makedirs("/opt/airflow/files/rates", exist_ok=True)
    with open("/opt/airflow/files/rates/forex_rates_raw.json", "w") as f:
        json.dump(filtered_rates, f, indent=2)

    print(f"Downloaded rates for {len(filtered_rates['rates'])} currencies")
    print(f"Rates: {filtered_rates['rates']}")

# Add this task in the DAG context:
download_rates = PythonOperator(
    task_id="download_rates",
    python_callable=download_forex_rates,
)
```

**Test:**
```bash
airflow tasks test forex_etl_pipeline download_rates 2024-01-01
# Check: /opt/airflow/files/rates/forex_rates_raw.json should exist
```

---

## Phase 4: Build the Transform and Load Tasks

Add the tasks that transform raw data into CSV, create the Postgres table, and load the data.

```python
import csv
from datetime import date
from airflow.providers.postgres.operators.postgres import PostgresOperator

def save_rates_to_csv():
    """
    Read the raw JSON rates file and write to CSV
    with a date column for partitioning.
    """
    with open("/opt/airflow/files/rates/forex_rates_raw.json") as f:
        data = json.load(f)

    today = date.today().isoformat()
    csv_path = f"/opt/airflow/files/rates/forex_rates_{today}.csv"

    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["base", "currency", "rate", "date"])
        writer.writeheader()
        for currency, rate in data["rates"].items():
            writer.writerow({
                "base": data["base"],
                "currency": currency,
                "rate": rate,
                "date": today,
            })

    print(f"Saved CSV to: {csv_path}")

# Task: Save to CSV
save_forex_rates = PythonOperator(
    task_id="save_rates_to_csv",
    python_callable=save_rates_to_csv,
)

# Task: Create the Postgres table
create_forex_rates_table = PostgresOperator(
    task_id="create_forex_rates_table",
    postgres_conn_id="postgres_default",
    sql="""
        CREATE TABLE IF NOT EXISTS forex_rates (
            id          SERIAL PRIMARY KEY,
            base        VARCHAR(10)    NOT NULL,
            currency    VARCHAR(10)    NOT NULL,
            rate        DECIMAL(20,6)  NOT NULL,
            date        DATE           NOT NULL,
            loaded_at   TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(base, currency, date)
        );
    """,
)

# Task: Insert data from CSV into Postgres
def insert_forex_rates_fn():
    """
    Read the CSV file and insert rows into Postgres.
    Uses INSERT ... ON CONFLICT DO UPDATE for idempotency.
    """
    import psycopg2
    from datetime import date

    today = date.today().isoformat()
    csv_path = f"/opt/airflow/files/rates/forex_rates_{today}.csv"

    conn = psycopg2.connect(
        host="postgres",
        database="airflow",
        user="airflow",
        password="airflow",
    )
    cursor = conn.cursor()

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute(
                """
                INSERT INTO forex_rates (base, currency, rate, date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (base, currency, date) DO UPDATE
                    SET rate = EXCLUDED.rate,
                        loaded_at = CURRENT_TIMESTAMP;
                """,
                (row["base"], row["currency"], float(row["rate"]), row["date"]),
            )

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Inserted rates for {today} into forex_rates table")

insert_forex_rates = PythonOperator(
    task_id="insert_forex_rates_into_table",
    python_callable=insert_forex_rates_fn,
)
```

**Test:**
```bash
airflow tasks test forex_etl_pipeline save_rates_to_csv 2024-01-01
airflow tasks test forex_etl_pipeline create_forex_rates_table 2024-01-01
airflow tasks test forex_etl_pipeline insert_forex_rates_into_table 2024-01-01
```

---

## Phase 5: Add Notification and Wire Everything Together

Add the notification task and define the full dependency chain.

```python
def send_notification():
    """
    Log a success message. In production, replace with
    an EmailOperator, SlackAPIOperator, or Teams notification.
    """
    from datetime import date
    today = date.today().isoformat()
    print("=" * 50)
    print(f"SUCCESS: Forex ETL Pipeline completed for {today}")
    print("Data has been loaded into the forex_rates table.")
    print("=" * 50)

notify_success = PythonOperator(
    task_id="notify_success",
    python_callable=send_notification,
)

# -------------------------------------------------------
# WIRE ALL TASKS TOGETHER — define the dependency chain
# -------------------------------------------------------
(
    check_forex_rates_available
    >> check_rates_file_available
    >> download_rates
    >> save_forex_rates
    >> create_forex_rates_table
    >> insert_forex_rates
    >> notify_success
)
```

**Final test — run the complete DAG:**
```bash
# Test every task in sequence
airflow dags test forex_etl_pipeline 2024-01-01
```

Or trigger it manually from the Airflow UI by clicking the play button on the DAG.

---

## Verifying the Results

```bash
# Connect to Postgres and verify the data was loaded
docker exec -it airflow-postgres-1 psql -U airflow -d airflow -c "
    SELECT base, currency, rate, date, loaded_at
    FROM forex_rates
    ORDER BY currency;
"

# Expected output:
#  base | currency |    rate    |    date    |         loaded_at
# ------+----------+------------+------------+----------------------------
#  EUR  | AUD      | 1.654200   | 2024-01-15 | 2024-01-15 08:00:01.234
#  EUR  | CAD      | 1.467000   | 2024-01-15 | 2024-01-15 08:00:01.234
#  EUR  | CHF      | 0.943000   | 2024-01-15 | 2024-01-15 08:00:01.234
#  ...
```

---

## Common Issues and Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `PoolNotFound` | Sensor times out | Increase `timeout` on HttpSensor |
| `FileNotFoundError` | `forex_currencies.json` missing | Create the file in `/opt/airflow/files/` |
| `Connection refused` on Postgres | Wrong host in connection | Use `postgres` (service name), not `localhost` |
| CSV file not found | Previous task failed | Check logs for the `save_rates_to_csv` task |
| Duplicate key violation | DAG ran twice same day | The `ON CONFLICT` clause handles this — should not happen |

---

## Stretch Goals

Once the basic pipeline works, try these enhancements:

1. **Add an EmailOperator** instead of the Python notification function
2. **Use XComs** to pass the CSV file path from `save_rates_to_csv` to `insert_forex_rates_into_table` instead of hardcoding it
3. **Add SLA** — add `sla=timedelta(hours=1)` to the DAG to alert if it does not complete within 1 hour
4. **Add a Pool** — create an `api_pool` with 1 slot and assign `download_rates` to it
5. **Parameterize the base currency** using Airflow Variables: `Variable.get("forex_base_currency", default_var="EUR")`

---

## 📂 Navigation

⬅️ **Prev:** [Project Guide](./Project_Guide.md) | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [Code Example](./Code_Example.md)
