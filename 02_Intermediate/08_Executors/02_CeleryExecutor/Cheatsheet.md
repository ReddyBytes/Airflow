# CeleryExecutor — Cheatsheet

> Quick reference for Apache Airflow 3. Distributed task execution with Celery + Redis or RabbitMQ.

---

## Core Configuration

```ini
# airflow.cfg
[core]
executor = CeleryExecutor

[celery]
broker_url = redis://redis:6379/0
result_backend = db+postgresql://airflow:airflow@postgres/airflow
worker_concurrency = 16
operation_timeout = 1.0

[celery_broker_transport_options]
visibility_timeout = 21600
```

```bash
# Environment variables
export AIRFLOW__CORE__EXECUTOR=CeleryExecutor
export AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0
export AIRFLOW__CELERY__RESULT_BACKEND=db+postgresql://airflow:airflow@postgres/airflow
export AIRFLOW__CELERY__WORKER_CONCURRENCY=16
```

---

## Key Configuration Parameters

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `[core] executor` | `AIRFLOW__CORE__EXECUTOR` | `SequentialExecutor` | Set to `CeleryExecutor` |
| `[celery] broker_url` | `AIRFLOW__CELERY__BROKER_URL` | — | Redis or RabbitMQ URL |
| `[celery] result_backend` | `AIRFLOW__CELERY__RESULT_BACKEND` | — | Where task results are stored |
| `[celery] worker_concurrency` | `AIRFLOW__CELERY__WORKER_CONCURRENCY` | `16` | Tasks per worker process |
| `[celery] operation_timeout` | `AIRFLOW__CELERY__OPERATION_TIMEOUT` | `1.0` | Celery operation timeout (seconds) |
| `[celery_broker_transport_options] visibility_timeout` | — | `21600` | Seconds before unACKed task is requeued |

---

## Broker URL Formats

```bash
# Redis (default port 6379, database 0)
redis://redis:6379/0

# Redis with password
redis://:mypassword@redis:6379/0

# Redis with SSL
rediss://redis:6379/0

# RabbitMQ (AMQP)
amqp://user:password@rabbitmq:5672/

# RabbitMQ with virtual host
amqp://user:password@rabbitmq:5672/airflow_vhost
```

---

## Result Backend Formats

```bash
# PostgreSQL (recommended — reuse existing metadata DB)
db+postgresql://airflow:airflow@postgres/airflow

# Redis (fast, but volatile — use persistent Redis)
redis://redis:6379/1

# RabbitMQ AMQP result backend (not recommended for large deployments)
rpc://
```

---

## Worker Commands

```bash
# Start a worker on the default queue
airflow celery worker

# Start on specific queues
airflow celery worker --queues default,heavy_tasks

# Start with custom concurrency
airflow celery worker --concurrency 8

# Start as daemon
airflow celery worker --daemonize

# Start Flower monitoring UI
airflow celery flower

# Start Flower on custom port
airflow celery flower --port=5556

# Check worker status
airflow celery status
```

---

## Queue Assignment in DAGs

```python
# Task-level queue assignment
from airflow.operators.python import PythonOperator

heavy = PythonOperator(
    task_id="heavy_job",
    python_callable=my_heavy_function,
    queue="heavy_tasks",        # Only workers with --queues heavy_tasks handle this
)

# Using @task decorator
from airflow.decorators import task

@task(queue="reporting")
def generate_report():
    pass
```

---

## Scaling Workers

```bash
# Docker Compose — scale to 5 workers
docker compose up --scale airflow-worker=5

# Docker Compose — scale down to 2 workers
docker compose up --scale airflow-worker=2

# Kubernetes — scale Celery worker deployment
kubectl scale deployment airflow-worker --replicas=10 -n airflow
```

---

## Redis vs RabbitMQ Comparison

| Feature | Redis | RabbitMQ |
|---|---|---|
| Setup complexity | Low | Medium |
| Latency | Very low | Low |
| Message persistence | Optional (`appendonly yes`) | Yes (durable queues) |
| Protocol | Redis protocol | AMQP |
| Best for | Most Airflow deployments | Advanced routing needs |
| Additional use | Cache, result backend | Dedicated message broker only |

---

## When to Use CeleryExecutor

| Condition | Use CeleryExecutor? |
|---|---|
| Single machine is a bottleneck | Yes |
| Need 50–1000+ concurrent tasks | Yes |
| Want to scale workers independently | Yes |
| Need per-queue task routing | Yes |
| Have Redis or RabbitMQ available | Yes |
| Running on a single machine with < 50 tasks | No — use LocalExecutor |
| Already on Kubernetes | Consider KubernetesExecutor instead |
| Need per-task container isolation | No — use KubernetesExecutor |

---

## Quick Architecture Reminder

```
Scheduler → Broker (Redis) → Workers (Celery)
                   ↕
             Result Backend (PostgreSQL)
                   ↕
              Scheduler reads result → updates DB
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Prev Executor** | [01_LocalExecutor](../01_LocalExecutor/) |
| **Next Executor** | [03_KubernetesExecutor](../03_KubernetesExecutor/) |
| **Section Root** | [08_Executors](../) |
