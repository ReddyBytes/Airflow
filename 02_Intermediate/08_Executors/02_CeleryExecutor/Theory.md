# CeleryExecutor in Apache Airflow 3

## 📂 Navigation
⬅️ **Prev: [LocalExecutor](../01_LocalExecutor/Theory.md)** | 🏠 **[Home](../../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [KubernetesExecutor](../03_KubernetesExecutor/Theory.md)**

---

## The Story: You Have Outgrown One Machine

Your Airflow deployment started small. A single VM, LocalExecutor, PostgreSQL — done. It handled 20 concurrent tasks comfortably. But your data platform has grown. You now have 15 data engineering teams, 200 DAGs, and peak hours where 150 tasks queue up simultaneously. Your scheduler machine has 16 CPUs and is pegged at 100% during peak windows. Tasks that should run in 10 minutes are sitting in the queue for 40 minutes waiting for a slot.

You try adding more CPUs to the VM. It helps a little, but the fundamental problem remains: **you have one machine, and it can only do so much work at once.**

You need to add more workers. Real, separate machines that can each execute tasks independently. When you need more capacity, you add a worker. When load drops off, you remove workers. The scheduler should not be doing the heavy lifting of running tasks — it should be doing the scheduling, and a fleet of workers should handle execution.

This is the problem `CeleryExecutor` solves.

---

## What Is CeleryExecutor?

`CeleryExecutor` is Airflow's distributed task execution engine. Instead of running tasks as local subprocesses on the scheduler machine, it sends tasks to a **message broker** (Redis or RabbitMQ), where **Celery worker processes** on separate machines pick them up and execute them.

Key properties:
- **Horizontal scaling**: add more worker machines to increase throughput
- **Decoupled workers**: workers are separate processes (often separate machines) from the scheduler
- **Queue-based routing**: tasks can be routed to specific worker pools using named queues
- **Fault tolerance**: if one worker crashes, its tasks are requeued and picked up by another worker
- **Flower dashboard**: a web UI for monitoring Celery workers and task queue depth

CeleryExecutor is the most commonly deployed executor for medium-to-large production Airflow installations.

---

## Architecture

```mermaid
flowchart TD
    subgraph Central["Central Airflow"]
        SCH[Scheduler]
        WEB[Webserver]
        DB[(PostgreSQL\nMetadata DB)]
        SCH <--> DB
        WEB <--> DB
    end

    subgraph Broker["Message Broker"]
        RD[(Redis / RabbitMQ\nTask Queue)]
        RB[(Result Backend\nRedis / PostgreSQL)]
    end

    subgraph Workers["Celery Worker Fleet"]
        W1[Worker 1\ndefault queue]
        W2[Worker 2\ndefault queue]
        W3[Worker 3\nheavy_tasks queue]
        W4[Worker 4\nheavy_tasks queue]
    end

    FLW[Flower UI\nWorker Monitor]

    SCH -->|"push task to queue"| RD
    RD -->|"worker picks up task"| W1
    RD -->|"worker picks up task"| W2
    RD -->|"worker picks up task"| W3
    RD -->|"worker picks up task"| W4
    W1 -->|"store result"| RB
    W2 -->|"store result"| RB
    W3 -->|"store result"| RB
    W4 -->|"store result"| RB
    RB -->|"scheduler reads result"| SCH
    FLW -.->|"monitor"| W1
    FLW -.->|"monitor"| W2
    FLW -.->|"monitor"| W3
    FLW -.->|"monitor"| W4

    style Central fill:#dbeafe,stroke:#2563eb
    style Broker fill:#fef9c3,stroke:#ca8a04
    style Workers fill:#dcfce7,stroke:#16a34a
    style SCH fill:#4a90d9,color:#fff
    style WEB fill:#4a90d9,color:#fff
    style FLW fill:#f97316,color:#fff
```

---

## Components in Detail

### 1. The Message Broker

The broker is the heart of CeleryExecutor. When the Airflow scheduler decides a task is ready to run, it does not run the task itself — it **pushes a message** to the broker's queue. That message says: "run DAG X, task Y, run_id Z."

Airflow supports two brokers:

**Redis** (most common):
- Simple to set up, low latency
- In-memory data structure store
- Persistent if configured correctly (`appendonly yes`)
- Best for most Airflow deployments
- Connection URL: `redis://redis:6379/0`

**RabbitMQ**:
- Full-featured message broker with AMQP protocol
- Better at queue guarantees and complex routing
- Higher operational overhead
- Connection URL: `amqp://user:pass@rabbitmq:5672/`

For most teams, Redis is the right choice. It is simpler and lower overhead.

### 2. Celery Workers

Workers are separate processes (usually on separate machines) that:
1. Connect to the broker and subscribe to one or more queues
2. Pull a task message from the queue
3. Execute the Airflow task (by running `airflow tasks run ...`)
4. Write the result (success/failure) to the result backend
5. Pull the next task

Workers run independently of the scheduler. You can add workers, remove workers, or restart workers without affecting the scheduler or other workers.

### 3. Result Backend

The result backend stores task execution results so the scheduler can check whether tasks succeeded or failed. Common options:
- **Redis** (same instance as broker, or separate)
- **PostgreSQL** (Airflow's metadata DB — convenient and already available)

Using PostgreSQL as the result backend is common because you already have it:

```ini
AIRFLOW__CELERY__RESULT_BACKEND = db+postgresql://airflow:airflow@postgres/airflow
```

### 4. Flower Dashboard

Flower is a lightweight web UI for monitoring Celery workers. It shows:
- Which workers are online and their current task counts
- Task queue depth per queue
- Success/failure rates
- Worker resource utilization

Run Flower as an additional service in your deployment:

```bash
airflow celery flower
```

Flower is available at port `5555` by default.

---

## Configuration

### Core Settings

```ini
# airflow.cfg
[core]
executor = CeleryExecutor

[celery]
# Broker URL — Redis
broker_url = redis://redis:6379/0

# Result backend — PostgreSQL (recommended)
result_backend = db+postgresql://airflow:airflow@postgres/airflow

# Max tasks each worker process handles concurrently
# Default: 16. Set to number of CPUs on the worker machine.
worker_concurrency = 16

# Timeout for celery tasks (seconds) — prevent hung tasks
operation_timeout = 1.0

[celery_broker_transport_options]
# Redis: visibility timeout (seconds). Tasks not ACKed within this window
# are requeued. Must be > your longest task duration.
visibility_timeout = 21600
```

### Environment Variables

```bash
export AIRFLOW__CORE__EXECUTOR=CeleryExecutor
export AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0
export AIRFLOW__CELERY__RESULT_BACKEND=db+postgresql://airflow:airflow@postgres/airflow
export AIRFLOW__CELERY__WORKER_CONCURRENCY=16
```

---

## Docker Compose Setup

```yaml
# docker-compose.yaml — CeleryExecutor with Redis

version: "3.8"

x-airflow-common:
  &airflow-common
  image: apache/airflow:3.0.0
  environment:
    &airflow-common-env
    AIRFLOW__CORE__EXECUTOR: CeleryExecutor
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CELERY__RESULT_BACKEND: db+postgresql://airflow:airflow@postgres/airflow
    AIRFLOW__CELERY__BROKER_URL: redis://redis:6379/0
    AIRFLOW__CORE__FERNET_KEY: "81HqDtbqAywKSOumSha3BhWNOdQ26slT6K0YaZeZyPs="
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
  volumes:
    - ./dags:/opt/airflow/dags
    - ./logs:/opt/airflow/logs
    - ./plugins:/opt/airflow/plugins
  depends_on:
    &airflow-common-depends-on
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - postgres-db-volume:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 5s
      retries: 5
    restart: always

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 30s
      retries: 50
    restart: always

  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"
    restart: always

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
    restart: always

  airflow-worker:
    <<: *airflow-common
    command: celery worker
    environment:
      <<: *airflow-common-env
      DUMB_INIT_SETSID: "0"
    restart: always

  airflow-flower:
    <<: *airflow-common
    command: celery flower
    ports:
      - "5555:5555"
    restart: always

  airflow-triggerer:
    <<: *airflow-common
    command: triggerer
    restart: always

  airflow-init:
    <<: *airflow-common
    entrypoint: /bin/bash
    command:
      - -c
      - |
        airflow db migrate
        airflow users create \
          --username admin --firstname Admin --lastname User \
          --role Admin --email admin@example.com --password admin
    environment:
      <<: *airflow-common-env

volumes:
  postgres-db-volume:
  redis-data:
```

---

## Scaling Workers

CeleryExecutor's killer feature is that you can scale workers independently of the scheduler.

### Docker Compose Scaling

```bash
# Scale to 5 worker containers on the same machine
docker compose up --scale airflow-worker=5

# Or set replicas in docker-compose.yaml
# airflow-worker:
#   deploy:
#     replicas: 3
```

### Separate Worker Machines

Add worker nodes on separate machines by running just the Celery worker command, pointing at the same broker and database:

```bash
# On worker machine 2 (install Airflow + same providers)
export AIRFLOW__CORE__EXECUTOR=CeleryExecutor
export AIRFLOW__CELERY__BROKER_URL=redis://redis-host:6379/0
export AIRFLOW__CELERY__RESULT_BACKEND=db+postgresql://airflow:airflow@postgres-host/airflow
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres-host/airflow

airflow celery worker --queues default,heavy_tasks
```

> Important: all worker machines must have the same DAG files, the same Airflow version, and the same provider packages installed.

---

## Celery Queues

Queues let you route specific tasks to specific workers. This is useful for:
- Running GPU tasks only on GPU-equipped workers
- Isolating expensive "heavy" tasks from quick "light" tasks
- Per-environment task routing (e.g., `prod` vs `dev` workers)

### Assigning a Task to a Queue

```python
from airflow.decorators import dag, task
from airflow.operators.python import PythonOperator
from datetime import datetime


@dag(
    dag_id="queue_routing_demo",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
)
def queue_routing_demo():

    # Runs on any worker listening to the "default" queue
    @task
    def light_task():
        print("Quick data validation — runs on any worker")

    # Runs only on workers started with --queues heavy_tasks
    @task(queue="heavy_tasks")
    def heavy_task():
        print("Heavy ML training — only GPU workers handle this")

    # Runs only on workers started with --queues reporting
    @task(queue="reporting")
    def generate_report():
        print("Report generation — dedicated reporting worker")

    light_task() >> heavy_task() >> generate_report()


queue_routing_demo()
```

### Starting Workers on Specific Queues

```bash
# Default worker — handles all tasks with no queue specified
airflow celery worker --queues default

# Heavy-task worker (GPU machine)
airflow celery worker --queues heavy_tasks

# Reporting worker
airflow celery worker --queues reporting

# A worker that handles multiple queues
airflow celery worker --queues default,reporting
```

---

## Monitoring with Flower

Flower is available at `http://localhost:5555` by default (or wherever you expose it).

What to look for in Flower:
- **Workers** tab: lists all connected workers, their status, and how many tasks they are running
- **Tasks** tab: shows recent task history, success/failure counts, execution time
- **Broker** tab: queue depth (backlog) — if this grows, you need more workers
- **Monitor** tab: real-time task rate graphs

```bash
# Start Flower manually
airflow celery flower

# Start on a custom port
airflow celery flower --port=5555

# With authentication
airflow celery flower --basic_auth=admin:secretpassword
```

---

## CeleryExecutor vs LocalExecutor vs KubernetesExecutor

| Feature | LocalExecutor | CeleryExecutor | KubernetesExecutor |
|---|---|---|---|
| **Task execution location** | Scheduler machine | Separate worker machines | Kubernetes pods |
| **Horizontal scaling** | No | Yes — add workers | Yes — cluster scales pods |
| **Message broker required** | No | Yes (Redis/RabbitMQ) | No |
| **Infrastructure complexity** | Low | Medium | High |
| **Task isolation** | Subprocess | Subprocess | Container (pod) |
| **Custom per-task environments** | No | No (all workers same env) | Yes (per-pod image) |
| **Idle resource cost** | Low | Medium (idle workers wait) | Very low (pods terminate) |
| **Queue-based routing** | No | Yes | Yes (via K8s node selectors) |
| **Best for** | Single machine, ≤50 tasks | Multi-machine, 50–1000s tasks | Cloud-native, K8s-first teams |
| **Monitoring UI** | None | Flower | Kubernetes dashboard |

---

## Key Takeaways

- `CeleryExecutor` separates task execution from the scheduler using a message broker (Redis or RabbitMQ).
- Workers are independent processes — add them to increase throughput, remove them to save cost.
- Use queues to route specific tasks to specific worker pools (GPU, heavy, reporting, etc.).
- Monitor workers and queue depth with Flower.
- The result backend (commonly the PostgreSQL metadata DB) stores task completion states.
- Upgrade from LocalExecutor to CeleryExecutor when one machine is not enough.

---

## 📂 Navigation
⬅️ **Prev: [LocalExecutor](../01_LocalExecutor/Theory.md)** | 🏠 **[Home](../../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [KubernetesExecutor](../03_KubernetesExecutor/Theory.md)**
