# Edge Executor — Interview Q&A

## 📂 Navigation
⬅️ **Prev: [New Auth Manager](../33_New_Auth_Manager/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)**

---

## Q1: What is the Edge Executor in Airflow 3?

The **Edge Executor** is a new executor type introduced in Airflow 3 that allows tasks to run on **remote, lightweight worker nodes** that communicate with the Airflow API Server over HTTP — without requiring a message broker (like Redis or RabbitMQ) or a direct database connection.

An edge worker is a standalone process that:
1. Polls the API Server for available tasks
2. Downloads the task payload
3. Executes the task locally
4. Reports results back to the API Server

This "outbound polling" model means edge workers can be deployed:
- Behind NAT / firewalls (they initiate connections, not receive them)
- On IoT devices and embedded systems
- At remote offices or data centers with limited connectivity
- On GPU/ML inference nodes that you do not want to grant DB access

---

## Q2: How does the Edge Executor architecture differ from the Celery Executor?

| | CeleryExecutor | EdgeExecutor |
|--|---------------|--------------|
| **Transport** | Redis or RabbitMQ message broker | HTTP to the Airflow API Server |
| **Worker initiation** | Subscribes to broker queue (receives push) | Polls API Server for tasks (pull model) |
| **Worker needs broker?** | Yes | No |
| **Worker needs DB access?** | No | No |
| **Worker needs inbound ports?** | No | No |
| **Scheduler → Worker path** | Scheduler → Broker → Worker | Scheduler → API Server → (polled by) Worker |
| **Best for** | Cloud VMs and containers in private network | Remote/edge nodes, IoT, isolated environments |
| **Horizontal scaling** | Add more workers subscribed to broker | Add more workers that poll the API |

The fundamental difference: Celery uses a **push** model (tasks arrive at the worker via the broker), while the Edge Executor uses a **pull** model (workers ask the API Server "do you have work for me?").

---

## Q3: What are the primary use cases for the Edge Executor?

**1. IoT and sensor data collection:**
Edge workers on Raspberry Pi units or industrial PLCs can run data collection tasks locally, then push results to central storage. The devices initiate all connections, requiring no inbound firewall rules.

**2. Remote field offices:**
A company with offices in regions with unreliable internet can run Airflow workers at each site. Tasks that must process local data run locally. Only the status reports need to reach the central API Server.

**3. ML inference at the edge:**
GPU nodes with expensive hardware can run as edge workers. You avoid giving these nodes database credentials or deploying a Redis broker to each datacenter. The GPU worker polls for inference tasks, runs them, and reports back.

**4. Multi-cloud task routing:**
An Airflow deployment in AWS needs to run some tasks in a Google Cloud environment where your ML models live. An edge worker in GCP polls the AWS-hosted API Server over HTTPS, pulls tasks, and runs them inside the GCP environment.

**5. Restricted security environments:**
Some organizations prohibit workers from having database access by policy. Edge workers have zero DB access — they communicate exclusively over HTTP with the API Server.

---

## Q4: How do edge workers register with the Airflow cluster?

Edge workers use a **self-registration** model. When you start an edge worker, it:

1. Makes an HTTP `POST` to the API Server's edge worker endpoint
2. Provides its name, queues it will accept tasks from, and heartbeat interval
3. The API Server records the worker in the metadata database
4. The worker begins polling the API Server at its configured heartbeat interval

```bash
# Starting an edge worker — it self-registers on startup
airflow edge worker \
  --queues edge_site_a,default \
  --worker-name "site-a-worker-01" \
  --api-url https://airflow.example.com
```

You can view registered edge workers in the UI under Admin > Workers, or via CLI:

```bash
airflow edge workers list
```

If a worker stops heartbeating (it crashed, or the network is down), the API Server marks it as offline after a configurable timeout. Tasks assigned to that worker are rescheduled.

---

## Q5: How do you route tasks to specific edge workers?

Task routing uses **queues**. Each edge worker subscribes to one or more named queues. Tasks specify which queue they should be placed on.

```python
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

with DAG("iot_pipeline", schedule="@hourly", start_date=datetime(2026, 1, 1)) as dag:

    # This task routes to workers listening on the "site_a_edge" queue
    collect_sensor_data = PythonOperator(
        task_id="collect_sensor_data",
        python_callable=read_sensors,
        queue="site_a_edge",       # Edge worker must subscribe to this queue
    )

    # This task runs on any worker (default queue)
    aggregate_readings = PythonOperator(
        task_id="aggregate_readings",
        python_callable=aggregate,
        queue="default",
    )

    collect_sensor_data >> aggregate_readings
```

The edge worker must have been started with `--queues site_a_edge` (or `site_a_edge,default`) to receive the `collect_sensor_data` task.

---

## Q6: Can the Celery Executor and Edge Executor run simultaneously?

No. An Airflow deployment uses **one executor at a time**, set globally in `airflow.cfg`:

```ini
[core]
executor = airflow.providers.edge.executors.edge_executor.EdgeExecutor
```

You cannot run CeleryExecutor and EdgeExecutor simultaneously in the same Airflow cluster.

However, you can mix edge workers and other worker patterns within EdgeExecutor by using queues. Some queues can be served by workers on powerful cloud VMs; other queues are served by lightweight edge nodes. The task's `queue` parameter determines where it runs.

---

## Q7: What are the limitations of the Edge Executor?

The Edge Executor is production-capable but has specific constraints:

**1. HTTP polling overhead:** Workers constantly poll the API Server. At high task volumes, this creates significant HTTP request load. For high-throughput pipelines, CeleryExecutor with Redis remains more efficient.

**2. Latency:** There is an inherent polling delay between when a task becomes ready and when a worker picks it up. The delay is bounded by the worker's poll interval (configurable, typically 5-30 seconds).

**3. No task priority within a queue:** Within a single queue, edge workers pick up tasks in FIFO order. CeleryExecutor supports more sophisticated priority mechanisms.

**4. DAG files must be accessible to workers:** Edge workers need access to your DAG code to execute tasks. This requires either a shared file system, a Git sync sidecar, or bundling DAG code in the edge worker's environment.

**5. Network reliability:** If the network between the edge worker and the API Server is intermittent, tasks can get stuck in "running" state until the timeout expires and they are rescheduled.

---

## Q8: How does task re-scheduling work when an edge worker goes offline?

The API Server maintains a heartbeat timeout for each registered edge worker. If a worker misses heartbeats for longer than `worker_heartbeat_timeout` seconds (default: 600 seconds), the API Server:

1. Marks the worker as **offline**
2. Identifies task instances that were in `running` state on that worker
3. Sets those task instances to `failed` or `up_for_retry` state (depending on the task's retry configuration)
4. Makes those tasks available for re-assignment to other workers

```ini
# airflow.cfg — tune heartbeat timeout
[edge]
worker_heartbeat_timeout = 300   # 5 minutes (default is 600)
poll_interval = 5                # How often workers poll for new tasks (seconds)
```

Tasks with `retries=3` will be retried on a healthy worker. Tasks with `retries=0` will be marked as failed and require manual re-trigger.

---

## Q9: What infrastructure does an edge worker need?

Minimal requirements:

- Python + `apache-airflow[edge]` installed
- Network access to the Airflow API Server over HTTPS (outbound only)
- Access to your DAG code (Git pull, mounted volume, or baked into a Docker image)
- An API token or credentials to authenticate with the API Server

Does NOT need:
- Redis, RabbitMQ, or any broker
- Database access (Postgres, MySQL)
- Inbound network connectivity (workers initiate all connections)
- The full Airflow Scheduler or API Server running locally

```bash
# Minimal edge worker installation
pip install "apache-airflow[edge]==3.0.0"

# Start the worker
AIRFLOW__CORE__EXECUTOR=airflow.providers.edge.executors.edge_executor.EdgeExecutor \
airflow edge worker \
  --queues default,iot_site_b \
  --api-url https://airflow.yourcompany.com \
  --worker-name "iot-site-b-worker"
```

---

## Q10: How do you monitor edge workers in production?

**Via Airflow UI:**
Navigate to Admin > Workers. You see each registered edge worker with:
- Name and queues
- Status (online/offline)
- Last heartbeat timestamp
- Currently assigned tasks

**Via CLI:**
```bash
# List all registered edge workers and their status
airflow edge workers list

# Show tasks currently assigned to a specific worker
airflow edge workers tasks --worker-name "site-a-worker-01"
```

**Via metrics:**
When Airflow is configured with StatsD or the Prometheus endpoint, edge worker metrics are emitted:
- `airflow.edge.worker.heartbeat` — timestamp of last heartbeat
- `airflow.edge.worker.running_tasks` — count of currently running tasks per worker
- `airflow.edge.worker.offline` — increments when a worker goes offline

**Alert setup:** Configure a Grafana alert on `airflow.edge.worker.offline` to get paged when a critical edge site goes down.

---

## Q11: Is the Edge Executor stable in Airflow 3.0?

The Edge Executor was introduced as a **beta feature** in Airflow 3.0. It is production-usable for workloads where its limitations are acceptable (moderate task volume, polling latency is tolerable), but some APIs may change in 3.x patch releases.

The Airflow community's guidance:
- Use it in production for edge/IoT use cases where it is the only feasible executor
- Do not use it as a replacement for CeleryExecutor in high-throughput data warehouse pipelines
- Follow the Airflow 3 release notes for stability updates

---

## 📂 Navigation
⬅️ **Prev: [New Auth Manager](../33_New_Auth_Manager/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)**
