# EdgeExecutor — Code Examples

> Apache Airflow 3. EdgeExecutor is new in Airflow 3. Examples show central configuration, edge worker setup, and DAG patterns for edge execution.

---

## 1. Central Airflow Configuration

```ini
# airflow.cfg — central Airflow instance (cloud or data centre)

[core]
# Run only EdgeExecutor (all tasks go to edge workers)
executor = EdgeExecutor

# OR run LocalExecutor + EdgeExecutor together:
# Tasks with no queue go to LocalExecutor (central machine)
# Tasks with a queue go to the matching edge worker
# executor = LocalExecutor,EdgeExecutor

[edge]
# URL of this Airflow instance — edge workers will poll this
api_url = https://airflow.mycompany.com

# How often edge workers poll for new tasks (seconds)
task_fetch_interval = 10

# How often edge workers send heartbeats (seconds)
heartbeat_interval = 30

# Mark a worker as offline if no heartbeat for this many seconds
worker_timeout = 120

[database]
sql_alchemy_conn = postgresql+psycopg2://airflow:airflow@postgres:5432/airflow
```

```bash
# Environment variables (for Docker / Kubernetes central deployment)
export AIRFLOW__CORE__EXECUTOR=EdgeExecutor
export AIRFLOW__EDGE__API_URL=https://airflow.mycompany.com
export AIRFLOW__EDGE__TASK_FETCH_INTERVAL=10
export AIRFLOW__EDGE__HEARTBEAT_INTERVAL=30
export AIRFLOW__EDGE__WORKER_TIMEOUT=120
```

---

## 2. Edge Worker Registration and Startup

```bash
# ── Step 1: On central Airflow — generate a token for the new edge worker ────
airflow edge worker create-token --worker-name store-001
# Output: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
# Copy this token — you will use it on the edge machine

# ── Step 2: On the edge machine — install Airflow edge support ───────────────
pip install "apache-airflow[edge]>=3.0.0"

# ── Step 3: On the edge machine — start the edge worker ─────────────────────
airflow edge worker start \
  --server-url https://airflow.mycompany.com \
  --worker-name store-001 \
  --token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... \
  --queue store-001

# ── Start with multiple queues ───────────────────────────────────────────────
airflow edge worker start \
  --server-url https://airflow.mycompany.com \
  --worker-name store-001 \
  --token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... \
  --queues store-001,default \
  --concurrency 4

# ── Start as a background daemon ─────────────────────────────────────────────
airflow edge worker start \
  --server-url https://airflow.mycompany.com \
  --worker-name store-001 \
  --token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... \
  --queue store-001 \
  --daemon

# ── Verify worker is registered ──────────────────────────────────────────────
# Run on central Airflow:
airflow edge worker list
```

---

## 3. Edge Worker as a `systemd` Service (Persistent Startup)

For production edge deployments, run the edge worker as a systemd service so it starts on boot and restarts on failure.

```ini
# /etc/systemd/system/airflow-edge-worker.service

[Unit]
Description=Airflow Edge Worker
After=network-online.target
Wants=network-online.target

[Service]
User=airflow
Group=airflow
WorkingDirectory=/opt/airflow
Environment="AIRFLOW__EDGE__API_URL=https://airflow.mycompany.com"
Environment="AIRFLOW__EDGE__WORKER_NAME=store-001"
Environment="AIRFLOW__EDGE__WORKER_TOKEN=eyJhbGci..."
Environment="AIRFLOW__EDGE__QUEUES=store-001"
Environment="AIRFLOW__EDGE__CONCURRENCY=4"
ExecStart=/usr/local/bin/airflow edge worker start
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=airflow-edge-worker

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable airflow-edge-worker
sudo systemctl start airflow-edge-worker

# Check status
sudo systemctl status airflow-edge-worker

# View logs
sudo journalctl -u airflow-edge-worker -f
```

---

## 4. Simple DAG Using Edge Workers

```python
# dags/store_daily_reconciliation.py

from airflow.decorators import dag, task
from datetime import datetime
from typing import dict as Dict


STORES = [
    {"id": "store-001", "name": "Downtown"},
    {"id": "store-002", "name": "Mall"},
    {"id": "store-003", "name": "Airport"},
]


@dag(
    dag_id="store_daily_reconciliation",
    description="Daily reconciliation for each retail store — runs on edge workers",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["retail", "edge", "reconciliation"],
)
def store_daily_reconciliation():
    """
    This DAG sends individual reconciliation tasks to edge workers at each store.
    The edge worker at store-001 handles its task locally, the one at store-002
    handles its task, etc.
    The final aggregation runs on central Airflow (no queue = default/local).
    """

    @task(queue="store-001")          # Runs on edge worker at store 001
    def reconcile_store_001(**context) -> dict:
        ds = context["ds"]
        print(f"[Store 001 - Downtown] Reconciling transactions for {ds}")
        # In production: read local POS database, validate totals
        transactions = 1_247
        discrepancies = 0
        return {"store_id": "store-001", "transactions": transactions, "discrepancies": discrepancies}

    @task(queue="store-002")          # Runs on edge worker at store 002
    def reconcile_store_002(**context) -> dict:
        ds = context["ds"]
        print(f"[Store 002 - Mall] Reconciling transactions for {ds}")
        transactions = 3_891
        discrepancies = 2
        return {"store_id": "store-002", "transactions": transactions, "discrepancies": discrepancies}

    @task(queue="store-003")          # Runs on edge worker at store 003
    def reconcile_store_003(**context) -> dict:
        ds = context["ds"]
        print(f"[Store 003 - Airport] Reconciling transactions for {ds}")
        transactions = 892
        discrepancies = 0
        return {"store_id": "store-003", "transactions": transactions, "discrepancies": discrepancies}

    @task                             # No queue = runs on central Airflow
    def aggregate_and_report(results: list) -> str:
        total_transactions = sum(r["transactions"] for r in results)
        total_discrepancies = sum(r["discrepancies"] for r in results)
        print(f"Daily Reconciliation Summary:")
        print(f"  Total transactions: {total_transactions:,}")
        print(f"  Total discrepancies: {total_discrepancies}")
        for r in results:
            status = "OK" if r["discrepancies"] == 0 else f"WARNING: {r['discrepancies']} discrepancies"
            print(f"  {r['store_id']}: {r['transactions']:,} transactions — {status}")
        return f"Processed {total_transactions:,} transactions across {len(results)} stores"

    r1 = reconcile_store_001()
    r2 = reconcile_store_002()
    r3 = reconcile_store_003()
    aggregate_and_report([r1, r2, r3])


store_daily_reconciliation()
```

---

## 5. Dynamic Edge Task Assignment (Many Sites)

For many edge sites, use Dynamic Task Mapping to avoid writing one task per site:

```python
# dags/fleet_sensor_collection.py

from airflow.decorators import dag, task
from datetime import datetime


EDGE_SITES = [
    {"site_id": "plant-01", "queue": "plant-01"},
    {"site_id": "plant-02", "queue": "plant-02"},
    {"site_id": "plant-03", "queue": "plant-03"},
    {"site_id": "warehouse-a", "queue": "warehouse-a"},
]


@dag(
    dag_id="fleet_sensor_collection",
    description="Collect sensor readings from all edge sites every 15 minutes",
    schedule="*/15 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["iot", "edge", "sensors"],
)
def fleet_sensor_collection():

    @task
    def get_sites() -> list:
        """Returns the list of sites to process. Could read from DB or config."""
        return EDGE_SITES

    @task
    def collect_sensors(site: dict) -> dict:
        """
        This task runs on the edge worker for the specified site.
        Note: Dynamic task mapping with per-task queue override requires
        using executor_config or the queue parameter on each expanded task.
        In practice for many sites, each site's task is defined explicitly
        or you pass the queue as context to a routing wrapper.
        """
        print(f"Collecting sensor data from {site['site_id']}")
        # In production: read from local sensor bus, MQTT, or Modbus
        return {
            "site_id": site["site_id"],
            "temperature_c": 22.4,
            "humidity_pct": 61.2,
            "pressure_kpa": 101.3,
        }

    @task
    def store_readings(readings: list) -> None:
        print(f"Storing {len(readings)} sensor readings to central time-series DB")
        for r in readings:
            print(f"  {r['site_id']}: {r['temperature_c']}°C, {r['humidity_pct']}% RH")

    sites = get_sites()
    readings = collect_sensors.expand(site=sites)
    store_readings(readings)


fleet_sensor_collection()
```

---

## 6. Token Rotation (Security Maintenance)

```bash
# Rotate the token for an edge worker (best practice: rotate every 90 days)
# Run on central Airflow:
airflow edge worker rotate-token --worker-name store-001
# Output: New token: eyJhbGci...

# Update the token on the edge machine:
# - Update the systemd service environment variable
# - Restart the service
sudo systemctl edit airflow-edge-worker
# Change: Environment="AIRFLOW__EDGE__WORKER_TOKEN=<new-token>"
sudo systemctl restart airflow-edge-worker

# Verify the worker reconnects with the new token:
airflow edge worker list
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Prev Executor** | [03_KubernetesExecutor](../03_KubernetesExecutor/) |
| **Section Root** | [08_Executors](../) |
