# EdgeExecutor — Cheatsheet

> Quick reference for Apache Airflow 3. Lightweight HTTP-polling executor for remote, resource-constrained, or intermittently connected sites.

---

## Setup: Central Airflow Instance

```ini
# airflow.cfg — on the central Airflow cluster

[core]
executor = EdgeExecutor

# Run both local tasks AND edge tasks simultaneously
# executor = LocalExecutor,EdgeExecutor

[edge]
api_url = https://airflow.mycompany.com
task_fetch_interval = 10     # Seconds between edge worker polls
heartbeat_interval = 30      # Seconds between worker heartbeats
worker_timeout = 120         # Mark worker offline after N seconds of silence
```

```bash
# Environment variables
export AIRFLOW__CORE__EXECUTOR=EdgeExecutor
export AIRFLOW__EDGE__API_URL=https://airflow.mycompany.com
export AIRFLOW__EDGE__TASK_FETCH_INTERVAL=10
export AIRFLOW__EDGE__HEARTBEAT_INTERVAL=30
```

---

## Setup: Edge Worker Machine

```bash
# Install Airflow with edge support on the remote machine
pip install "apache-airflow[edge]>=3.0.0"
# Or explicitly:
pip install apache-airflow apache-airflow-providers-edge
```

```ini
# airflow.cfg on the edge machine (minimal)
[edge]
api_url = https://airflow.mycompany.com
worker_token = eyJhbGci...     # Token generated on central Airflow
worker_name = store-001        # Unique per worker
queues = store-001             # Queue(s) this worker listens on
concurrency = 4                # Max concurrent tasks on this worker
poll_interval = 10             # Seconds between polls
```

---

## Edge Worker Commands

```bash
# Generate a token for a new edge worker (run on central Airflow)
airflow edge worker create-token --worker-name store-001

# Start the edge worker (run on the edge machine)
airflow edge worker start \
  --server-url https://airflow.mycompany.com \
  --worker-name store-001 \
  --token eyJhbGci... \
  --queue store-001

# Start with multiple queues
airflow edge worker start \
  --server-url https://airflow.mycompany.com \
  --worker-name store-001 \
  --token eyJhbGci... \
  --queues store-001,default

# Start as a background daemon
airflow edge worker start --daemon

# Stop the edge worker
airflow edge worker stop

# List all registered edge workers (run on central Airflow)
airflow edge worker list

# Rotate a worker token (security best practice)
airflow edge worker rotate-token --worker-name store-001

# Deregister a worker
airflow edge worker deregister --worker-name store-001
```

---

## Routing Tasks to Edge Workers

```python
# Route to a specific edge worker by queue name
from airflow.operators.python import PythonOperator

store_task = PythonOperator(
    task_id="process_store_001",
    python_callable=reconcile_store,
    queue="store-001",           # Only the worker at store-001 handles this
)

# Using @task decorator
from airflow.decorators import task

@task(queue="factory-floor-a")
def run_quality_check():
    pass
```

---

## Key Configuration Parameters

| Parameter | Description |
|---|---|
| `[edge] api_url` | URL of the central Airflow webserver API |
| `[edge] task_fetch_interval` | Seconds between worker polls for new tasks |
| `[edge] heartbeat_interval` | Seconds between worker heartbeats |
| `[edge] worker_timeout` | Seconds of silence before worker is marked offline |
| `[edge] worker_token` | Auth token for the edge worker (on edge machine) |
| `[edge] worker_name` | Unique identifier for this edge worker |
| `[edge] queues` | Comma-separated list of queues this worker listens on |
| `[edge] concurrency` | Max tasks running simultaneously on this worker |

---

## Executor Comparison

| Feature | LocalExecutor | CeleryExecutor | KubernetesExecutor | EdgeExecutor |
|---|---|---|---|---|
| Location | Scheduler machine | Dedicated workers | K8s pods | Remote edge machines |
| Broker required | No | Yes | No | No |
| Offline capable | N/A | No | No | Yes |
| Footprint | Medium | Medium | Large | Very small |
| Network | None | Persistent | K8s API | Intermittent HTTP OK |
| Best for | Single-machine prod | High throughput | Cloud-native | IoT / remote sites |

---

## When to Use EdgeExecutor

| Condition | Use EdgeExecutor? |
|---|---|
| Tasks must run on remote/on-premise machines | Yes |
| Network connectivity is intermittent | Yes |
| IoT sensors, factory floors, retail stores | Yes |
| Data cannot leave a site (compliance) | Yes |
| High-throughput centralised workloads | No — use CeleryExecutor |
| Running on Kubernetes | No — use KubernetesExecutor |
| All tasks run in one data centre | No — use LocalExecutor or CeleryExecutor |

---

## Security Best Practices

```bash
# 1. Always use HTTPS for api_url (never plain HTTP in production)
# 2. Generate a unique token per edge worker
# 3. Rotate tokens periodically
airflow edge worker rotate-token --worker-name store-001

# 4. Use Airflow secrets backend for token storage on edge machines
# 5. Restrict each worker to only its own queue
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Prev Executor** | [03_KubernetesExecutor](../03_KubernetesExecutor/) |
| **Section Root** | [08_Executors](../) |
