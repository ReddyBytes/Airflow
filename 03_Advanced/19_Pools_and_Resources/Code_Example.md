# Pools and Resources — Code Examples

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Monitoring and Alerting](../20_Monitoring_and_Alerting/Theory.md)**

---

## Example 1: Creating Pools via UI and CLI

### Via CLI (fastest for scripting and automation)

```bash
# Create a pool with 5 slots
airflow pools set db_pool 5 "Limits concurrent PostgreSQL connections"

# Create a pool for external API rate limiting
airflow pools set api_pool 3 "Max 3 concurrent calls to the external reporting API"

# Create a pool for memory-intensive ML jobs
airflow pools set ml_pool 2 "Max 2 concurrent ML training jobs"

# List all pools
airflow pools list

# Get details for a specific pool
airflow pools get db_pool

# Delete a pool (only if no tasks are currently assigned to it)
airflow pools delete old_pool
```

### Via bulk import (recommended for production — version-controlled)

```json
// pools.json — commit this file to your repo
[
  {
    "name": "db_pool",
    "slots": 5,
    "description": "Limits concurrent PostgreSQL connections to protect the DB",
    "include_deferred": false
  },
  {
    "name": "api_pool",
    "slots": 3,
    "description": "External reporting API — max 3 concurrent requests"
  },
  {
    "name": "ml_pool",
    "slots": 2,
    "description": "Memory-intensive ML training — max 2 concurrent jobs"
  }
]
```

```bash
# Import all pools at once (idempotent — safe to re-run on every deploy)
airflow pools import pools.json

# Export current pool configuration (useful for auditing)
airflow pools export pools_backup.json
```

### Via UI

Navigate to **Admin > Pools** in the Airflow UI, then click the **+** button and fill in the form.

---

## Example 2: Assigning Tasks to Pools

```python
# dags/pool_assignment_demo.py
"""
Demonstrates the pool parameter on various operator types.
"""
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from datetime import datetime


def query_database():
    print("Running database query...")


def call_external_api():
    print("Calling external API...")


def train_model():
    print("Training ML model — this uses a lot of RAM...")


with DAG(
    dag_id="pool_assignment_demo",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    # ── Assign to db_pool ─────────────────────────────────────────────────────
    query_sales = PythonOperator(
        task_id="query_sales",
        python_callable=query_database,
        pool="db_pool",          # Only runs when db_pool has a free slot
        pool_slots=1,            # Consumes 1 of the 5 available slots (default)
    )

    query_inventory = SQLExecuteQueryOperator(
        task_id="query_inventory",
        conn_id="postgres_default",
        sql="SELECT count(*) FROM inventory WHERE updated_at > '{{ ds }}'",
        pool="db_pool",          # Also competes for db_pool slots
        pool_slots=1,
    )

    # ── Assign to api_pool ────────────────────────────────────────────────────
    fetch_exchange_rates = PythonOperator(
        task_id="fetch_exchange_rates",
        python_callable=call_external_api,
        pool="api_pool",
        pool_slots=1,
    )

    # ── Assign to ml_pool — consumes 2 slots (takes all of ml_pool) ──────────
    train_fraud_model = PythonOperator(
        task_id="train_fraud_model",
        python_callable=train_model,
        pool="ml_pool",
        pool_slots=2,     # This job is so heavy it needs BOTH ml_pool slots
                          # Nothing else in ml_pool will run while this runs
    )

    # ── No pool — runs on default_pool (128 slots by default) ─────────────────
    send_report = BashOperator(
        task_id="send_report",
        bash_command='echo "Report sent"',
        # No pool= parameter → uses default_pool
    )

    [query_sales, query_inventory] >> fetch_exchange_rates >> train_fraud_model >> send_report
```

---

## Example 3: Priority Weight

`priority_weight` controls the queue order when multiple tasks are waiting for a pool slot. Higher value = picked first.

```python
# dags/priority_weight_demo.py
"""
Scenario: db_pool has 3 slots. We have 10 DB tasks all queued at the same time.
Some are critical and must run first.
"""
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime


def run_query(query_name: str):
    import time
    print(f"Running query: {query_name}")
    time.sleep(5)


with DAG(
    dag_id="priority_weight_demo",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    # ── Critical tasks — pick these first ─────────────────────────────────────
    exec_dashboard = PythonOperator(
        task_id="exec_dashboard_query",
        python_callable=run_query,
        op_kwargs={"query_name": "exec_dashboard"},
        pool="db_pool",
        priority_weight=100,  # Highest priority — goes to front of queue
    )

    sla_report = PythonOperator(
        task_id="sla_report_query",
        python_callable=run_query,
        op_kwargs={"query_name": "sla_report"},
        pool="db_pool",
        priority_weight=50,   # High priority
    )

    # ── Standard tasks — run when slots free up ───────────────────────────────
    daily_summary = PythonOperator(
        task_id="daily_summary",
        python_callable=run_query,
        op_kwargs={"query_name": "daily_summary"},
        pool="db_pool",
        priority_weight=10,   # Normal priority
    )

    # ── Background/batch tasks — run last ─────────────────────────────────────
    archive_old_data = PythonOperator(
        task_id="archive_old_data",
        python_callable=run_query,
        op_kwargs={"query_name": "archive"},
        pool="db_pool",
        priority_weight=1,    # Lowest priority — runs only when nothing else is queued
    )

    historical_backfill = PythonOperator(
        task_id="historical_backfill",
        python_callable=run_query,
        op_kwargs={"query_name": "backfill"},
        pool="db_pool",
        priority_weight=1,
    )
```

---

## Example 4: Pool Slots Management (Dynamic Adjustment)

You can change pool slot counts without restarting Airflow:

```bash
# Check current state of all pools
airflow pools list

# Example output:
# Pool          Slots  Running  Queued  Deferred  Open
# default_pool  128    5        12      0         111
# db_pool       5      3        2       0         0     <-- 2 tasks queued, consider increasing
# api_pool      3      2        0       0         1

# Increase db_pool during a heavy migration (temporary)
airflow pools set db_pool 10 "Temporarily expanded for Q1 migration"

# Scale back down after migration
airflow pools set db_pool 5 "Back to normal — max 5 DB connections"

# Quick formula: pool_slots ≈ (DB max_connections × 0.8) / number_of_environments
# Example: Postgres max_connections=100, 3 envs → 100 * 0.8 / 3 ≈ 26 slots per env
```

Automating pool adjustment via the REST API:

```python
# scripts/adjust_pool.py
"""
Dynamically resize a pool using the Airflow REST API.
Useful for scheduled maintenance windows.
"""
import requests
import os

AIRFLOW_API_URL = os.environ.get("AIRFLOW_API_URL", "http://localhost:8080")
AIRFLOW_TOKEN   = os.environ.get("AIRFLOW_API_TOKEN", "")

def set_pool_slots(pool_name: str, new_slots: int, description: str = "") -> dict:
    response = requests.patch(
        f"{AIRFLOW_API_URL}/api/v2/pools/{pool_name}",
        json={"slots": new_slots, "description": description},
        headers={
            "Authorization": f"Bearer {AIRFLOW_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    response.raise_for_status()
    return response.json()


# Expand pool before a big load
result = set_pool_slots("db_pool", 10, "Expanded for nightly load window")
print(f"db_pool now has {result['slots']} slots")
```

---

## Example 5: DAG with Multiple Pools

A realistic ETL pipeline where different stages compete for different resource pools.

```python
# dags/multi_pool_etl.py
"""
Multi-stage ETL pipeline demonstrating pool usage at each stage.

Stage 1 (Extract): db_pool — reads from PostgreSQL (limited connections)
Stage 2 (Transform): default_pool — CPU-bound, no shared resource limit needed
Stage 3 (API Enrich): api_pool — calls rate-limited external API
Stage 4 (ML Score): ml_pool — memory-intensive scoring
Stage 5 (Load): db_pool — writes back to PostgreSQL
"""
from airflow.sdk import DAG
from airflow.decorators import task
from datetime import datetime


with DAG(
    dag_id="multi_pool_etl",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pools-demo", "etl"],
) as dag:

    @task(pool="db_pool", pool_slots=1)
    def extract_orders(**context):
        """Read orders from PostgreSQL — respects db_pool limit."""
        print(f"Extracting orders for {context['ds']}")
        return {"row_count": 50000}

    @task(pool="db_pool", pool_slots=1)
    def extract_customers(**context):
        """Read customers from PostgreSQL — also uses db_pool."""
        print(f"Extracting customers for {context['ds']}")
        return {"row_count": 10000}

    @task  # No pool — uses default_pool
    def transform(orders: dict, customers: dict):
        """CPU-bound join — no shared resource limits needed."""
        print(f"Joining {orders['row_count']} orders with {customers['row_count']} customers")
        return {"joined_rows": orders["row_count"]}

    @task(pool="api_pool", pool_slots=1)
    def enrich_with_geo(joined: dict):
        """Call external geocoding API — respects api_pool rate limit."""
        print(f"Enriching {joined['joined_rows']} rows with geo data")
        return joined

    @task(pool="ml_pool", pool_slots=2)
    def score_churn_risk(enriched: dict):
        """ML scoring — heavy memory usage, takes both ml_pool slots."""
        print("Running churn risk model (high-memory operation)...")
        return {"scored_rows": enriched["joined_rows"]}

    @task(pool="db_pool", pool_slots=1, priority_weight=5)
    def load_results(scored: dict):
        """Write scored results back to PostgreSQL — uses db_pool for the write."""
        print(f"Loading {scored['scored_rows']} scored rows to PostgreSQL")

    # Wire up the DAG
    orders    = extract_orders()
    customers = extract_customers()
    joined    = transform(orders, customers)
    enriched  = enrich_with_geo(joined)
    scored    = score_churn_risk(enriched)
    load_results(scored)
```

---

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Monitoring and Alerting](../20_Monitoring_and_Alerting/Theory.md)**
