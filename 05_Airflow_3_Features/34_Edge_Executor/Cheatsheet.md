# Edge Executor — Cheatsheet

## Navigation
⬅️ **Prev: [New Auth Manager](../33_New_Auth_Manager/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)**

---

## Setup: Central Airflow Cluster

```ini
# airflow.cfg — central cluster
[core]
executor = EdgeExecutor

# Combined: local + edge tasks
executor = LocalExecutor,EdgeExecutor

[edge]
api_url = https://airflow.company.internal:8080
task_fetch_interval = 5  # seconds
```

---

## Setup: Edge Worker Machine

```bash
# Install
pip install "apache-airflow[edge]>=3.0.0"
```

```ini
# airflow.cfg on edge machine
[edge]
api_url = https://airflow.company.internal:8080
worker_token = your-secure-token
worker_name = edge-worker-01       # unique per worker
queues = queue_name,another_queue  # which queues to consume
poll_interval = 10                 # seconds between polls
concurrency = 4                    # max concurrent tasks
```

---

## Edge Worker Commands

```bash
# Start worker
airflow edge worker start

# Start with specific queues
airflow edge worker start --queues factory_floor,gpu_tasks

# Start with concurrency limit
airflow edge worker start --concurrency 4

# Start as daemon
airflow edge worker start --daemon

# Stop worker
airflow edge worker stop

# List registered edge workers
airflow edge worker list

# Check worker status
airflow edge worker status --worker-name edge-worker-01
```

---

## Assigning Tasks to Edge Workers

```python
# Route task to specific edge queue
task = PythonOperator(
    task_id="edge_task",
    python_callable=my_function,
    queue="factory_floor",    # must match worker's queue config
)

# Using @task decorator
@task(queue="gpu_workers")
def run_training():
    pass
```

---

## Executor Comparison Table

| Feature | Local | Celery | Kubernetes | Edge |
|---------|-------|--------|-----------|------|
| Broker needed | No | Yes | No | No |
| DB access from worker | Yes | Yes | Yes | No — API only |
| Horizontal scale | No | Yes | Yes | Yes |
| Remote nodes | No | Partial | No | Yes |
| IoT/edge support | No | No | No | Yes |
| Task isolation | Process | Process | Container | Process |
| Overhead | Low | Medium | Medium | Very low |

---

## Worker Registration and Token Security

```bash
# Generate a worker token (on central Airflow)
airflow edge worker create-token --worker-name edge-worker-01

# Rotate a token
airflow edge worker rotate-token --worker-name edge-worker-01

# Deregister a worker
airflow edge worker deregister --worker-name edge-worker-01
```

---

## Key Limitations

| Limitation | Detail |
|-----------|--------|
| Token security | Token grants task execution access — protect and rotate it |
| Network drop | Worker stops receiving tasks; resumes on reconnect |
| Log streaming | Slight delay vs central workers |
| Python env | Manage dependencies on edge machine manually |
| DAG file access | Edge machine must have DAG files (sync separately) |

---

## Navigation
⬅️ **Prev: [New Auth Manager](../33_New_Auth_Manager/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)**
