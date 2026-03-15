# Edge Executor — Code Examples

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)**

---

## Example 1: Enabling the Edge Executor

The Edge Executor requires the `apache-airflow-providers-edge` package. Configure it in `airflow.cfg` or via environment variables.

```bash
# Install the provider
pip install apache-airflow-providers-edge
```

```ini
# airflow.cfg — enable Edge Executor globally
[core]
executor = airflow.providers.edge.executors.edge_executor.EdgeExecutor

[edge]
# How often edge workers poll the API Server for new tasks (seconds)
poll_interval = 5

# How long (seconds) to wait before marking a worker as offline
# if it stops sending heartbeats
worker_heartbeat_timeout = 300

# How many tasks a single edge worker will run concurrently
worker_concurrency = 4

# API Server URL that edge workers will connect to
api_url = https://airflow.yourcompany.com
```

Using environment variables (Docker / Kubernetes):

```yaml
# docker-compose.yml
environment:
  AIRFLOW__CORE__EXECUTOR: airflow.providers.edge.executors.edge_executor.EdgeExecutor
  AIRFLOW__EDGE__POLL_INTERVAL: "5"
  AIRFLOW__EDGE__WORKER_HEARTBEAT_TIMEOUT: "300"
  AIRFLOW__EDGE__WORKER_CONCURRENCY: "4"
  AIRFLOW__EDGE__API_URL: "https://airflow.yourcompany.com"
```

---

## Example 2: Starting an Edge Worker

An edge worker is a standalone process. It does not need a broker, database connection, or any Airflow components running locally — only the `airflow` package and network access to the API Server.

```bash
# Basic startup — subscribes to the "default" queue
airflow edge worker

# Subscribe to multiple queues
airflow edge worker \
  --queues default,iot_sensors,gpu_inference \
  --worker-name "site-a-edge-node-01"

# Point to a remote API Server
airflow edge worker \
  --queues iot_sensors \
  --worker-name "factory-floor-worker" \
  --api-url https://airflow.hq.example.com

# Set worker concurrency (overrides airflow.cfg for this instance)
airflow edge worker \
  --queues default \
  --worker-name "heavy-worker" \
  --concurrency 2    # Only 2 simultaneous tasks on this node
```

### Minimal Docker image for an edge worker

```dockerfile
# Dockerfile.edge-worker
# Minimal image: only Airflow + edge provider + your DAG dependencies
FROM python:3.11-slim

RUN pip install --no-cache-dir \
    "apache-airflow==3.0.0" \
    "apache-airflow-providers-edge" \
    pandas \
    boto3

# Copy only the DAG files this worker needs to execute
COPY dags/ /opt/airflow/dags/

ENV AIRFLOW__CORE__EXECUTOR=airflow.providers.edge.executors.edge_executor.EdgeExecutor
ENV AIRFLOW__EDGE__API_URL=https://airflow.yourcompany.com

CMD ["airflow", "edge", "worker", "--queues", "default", "--worker-name", "docker-edge-01"]
```

```bash
# Build and run
docker build -t my-edge-worker -f Dockerfile.edge-worker .
docker run -d \
  -e AIRFLOW__EDGE__API_URL=https://airflow.yourcompany.com \
  -e AIRFLOW__EDGE__WORKER_API_TOKEN=your_api_token \
  my-edge-worker
```

---

## Example 3: Routing Tasks to Edge Workers

Use the `queue` parameter to direct tasks to specific edge workers.

```python
# dags/multi_site_pipeline.py
"""
Pipeline that collects data from two remote factory sites,
then aggregates in the central cloud environment.

site_a_edge worker: runs on factory floor in Site A
site_b_edge worker: runs on factory floor in Site B
default queue:      runs on central cloud workers
"""
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime


def collect_site_a_data():
    """Runs directly on the Site A edge worker — reads local sensors."""
    import json
    readings = {"temp": 72.4, "pressure": 14.7, "timestamp": "2026-03-15T10:00:00"}
    with open("/tmp/site_a_readings.json", "w") as f:
        json.dump(readings, f)
    print(f"Collected {len(readings)} readings from Site A")


def collect_site_b_data():
    """Runs directly on the Site B edge worker — reads local sensors."""
    import json
    readings = {"temp": 68.1, "pressure": 14.9, "timestamp": "2026-03-15T10:00:00"}
    with open("/tmp/site_b_readings.json", "w") as f:
        json.dump(readings, f)
    print(f"Collected {len(readings)} readings from Site B")


def aggregate_readings():
    """Runs in the central cloud — combines data from both sites."""
    # In practice, both edge tasks would have uploaded to S3/GCS first
    print("Aggregating readings from Site A and Site B...")
    print("Generating combined report...")


with DAG(
    dag_id="multi_site_pipeline",
    schedule="@hourly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["edge-executor", "iot"],
) as dag:

    # Route to Site A's edge worker
    site_a_collect = PythonOperator(
        task_id="collect_site_a",
        python_callable=collect_site_a_data,
        queue="site_a_edge",          # Must match --queues on the Site A edge worker
    )

    # Route to Site B's edge worker
    site_b_collect = PythonOperator(
        task_id="collect_site_b",
        python_callable=collect_site_b_data,
        queue="site_b_edge",          # Must match --queues on the Site B edge worker
    )

    # Aggregate in the central environment (no queue = uses "default")
    aggregate = PythonOperator(
        task_id="aggregate",
        python_callable=aggregate_readings,
        queue="default",
    )

    [site_a_collect, site_b_collect] >> aggregate
```

---

## Example 4: Queue Configuration Best Practices

```python
# dags/queue_routing_examples.py
"""
Demonstrates different queue routing patterns for edge deployments.
"""
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime

with DAG(
    dag_id="queue_routing_demo",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    # ── Pattern 1: Hardware-specific queue ────────────────────────────────────
    # Tasks that need a GPU run on workers started with --queues gpu_workers
    gpu_task = PythonOperator(
        task_id="ml_inference",
        python_callable=lambda: print("Running ML inference on GPU"),
        queue="gpu_workers",
    )

    # ── Pattern 2: Location-specific queue ───────────────────────────────────
    # Tasks that must process local files on a remote worker
    local_file_task = PythonOperator(
        task_id="read_local_sensor_file",
        python_callable=lambda: print("Reading /mnt/sensors/latest.csv"),
        queue="factory_floor_01",
    )

    # ── Pattern 3: High-memory queue ─────────────────────────────────────────
    # Route memory-intensive tasks to high-RAM workers
    memory_task = PythonOperator(
        task_id="large_data_join",
        python_callable=lambda: print("Joining 50GB datasets"),
        queue="high_memory",
    )

    # ── Pattern 4: Default queue (no edge requirement) ────────────────────────
    # Falls back to any available worker on the default queue
    notification_task = BashOperator(
        task_id="send_notification",
        bash_command='echo "Pipeline complete"',
        queue="default",   # or omit queue — default is the default
    )

    [gpu_task, local_file_task, memory_task] >> notification_task
```

### Corresponding worker startup commands

```bash
# Start a GPU worker subscribed to the gpu_workers queue
airflow edge worker \
  --queues gpu_workers,default \
  --worker-name "gpu-node-01" \
  --concurrency 1    # Only 1 task at a time on this GPU

# Start the factory floor worker — subscribes to its specific queue
airflow edge worker \
  --queues factory_floor_01 \
  --worker-name "factory-01" \
  --concurrency 4

# Start a high-memory worker
airflow edge worker \
  --queues high_memory,default \
  --worker-name "big-ram-server" \
  --concurrency 2

# List all workers and their current queue assignments
airflow edge workers list
```

---

## Example 5: Monitoring Edge Workers via CLI

```bash
# ── View worker status ────────────────────────────────────────────────────────

# List all registered edge workers
airflow edge workers list

# Example output:
# worker_name          status   queues                    last_heartbeat         running_tasks
# site-a-edge-node-01  online   site_a_edge,default       2026-03-15T10:05:00    2
# gpu-node-01          online   gpu_workers,default       2026-03-15T10:04:58    1
# factory-floor-01     offline  factory_floor_01          2026-03-15T09:45:00    0  <-- no heartbeat

# ── Check tasks on a specific worker ─────────────────────────────────────────
airflow edge workers tasks --worker-name "site-a-edge-node-01"

# ── Graceful shutdown ─────────────────────────────────────────────────────────
# On the worker machine — let current tasks finish before stopping
airflow edge worker stop --graceful --timeout 300

# ── Force shutdown (immediate, tasks get rescheduled) ─────────────────────────
airflow edge worker stop --force

# ── Check connectivity from an edge node (useful for debugging) ──────────────
curl -s https://airflow.yourcompany.com/api/v2/health
# Expected: {"metadatabase": {"status": "healthy"}, "scheduler": {"status": "healthy"}}
```

---

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)**
