# Airflow 3 Architecture — Cheatsheet

## All Components at a Glance

| Component | Role | Port | Process Command | Config Section | Scalable? |
|---|---|---|---|---|---|
| **API Server** | Serves Web UI + REST API | 8080 | `airflow api-server` | `[api]` | Yes |
| **Scheduler** | Schedules tasks (no DAG parsing) | — | `airflow scheduler` | `[scheduler]` | Yes (HA) |
| **DAG Processor** | Parses DAG files, serializes to DB | — | `airflow dag-processor` | `[dag_processor]` | Limited |
| **Worker (Celery)** | Executes tasks | — | `airflow celery worker` | `[celery]` | Yes |
| **Triggerer** | Handles deferrable operators (async) | — | `airflow triggerer` | `[triggerer]` | Yes |
| **Internal API** | HTTP bridge between components and DB | (embedded) | (part of api-server) | `[api]` | Via API Server |
| **Metadata DB** | Stores DAGs, runs, task states, XComs | 5432 | `postgres` | `[database]` | Via Postgres HA |
| **Message Broker** | Task queue (CeleryExecutor only) | 6379 | `redis-server` | `[celery]` | Via Redis Cluster |

---

## Airflow 2 → Airflow 3 Key Changes

| What | Airflow 2 | Airflow 3 |
|---|---|---|
| DAG Parsing | Inside Scheduler | Standalone DAG Processor |
| Web UI process | `airflow webserver` | `airflow api-server` |
| REST API | Separate from webserver | Same process as UI (API Server) |
| DB access | Direct from most components | Only through Internal API |
| Edge deployments | Not supported natively | Edge Executor (new) |
| DB command | `airflow db init` | `airflow db migrate` |

---

## Component Startup Commands (Manual / Bare Metal)

```bash
# Step 1 — Initialize the database (run once)
airflow db migrate

# Step 2 — Create an admin user (run once)
airflow users create \
  --username admin \
  --password admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com

# Step 3 — Start all components (each in its own terminal or as a service)
airflow api-server        # Web UI + REST API on :8080
airflow scheduler         # Scheduling loop
airflow dag-processor     # DAG file parsing
airflow triggerer          # Deferrable operators (optional but recommended)
airflow celery worker     # Only if using CeleryExecutor
```

---

## Docker Compose Services (Airflow 3)

| Service Name | Airflow Component |
|---|---|
| `airflow-apiserver` | API Server (replaces webserver) |
| `airflow-scheduler` | Scheduler |
| `airflow-dag-processor` | DAG Processor (NEW — was not a separate service in v2) |
| `airflow-worker` | Celery Worker |
| `airflow-triggerer` | Triggerer |
| `postgres` | Metadata Database |
| `redis` | Message Broker (CeleryExecutor only) |

---

## Architecture Mental Model

```
DAG files (Python)
    ↓  [read by]
DAG Processor  →  Internal API  →  Metadata DB
                                        ↑
Scheduler  →  Internal API  →  Metadata DB
    ↓  [submits task]
Executor  →  (Broker if Celery)  →  Worker
                                        ↓
                                  Internal API  →  Metadata DB
                                  (reports result)

API Server  →  Internal API  →  Metadata DB
(browser / REST)
```

---

## Key Config Values

```ini
# airflow.cfg

[core]
executor = CeleryExecutor        # or LocalExecutor, KubernetesExecutor, EdgeExecutor

[database]
sql_alchemy_conn = postgresql+psycopg2://airflow:airflow@postgres/airflow

[scheduler]
scheduler_heartbeat_sec = 5

[dag_processor]
dag_file_processor_timeout = 50

[celery]
broker_url = redis://redis:6379/0
result_backend = db+postgresql://airflow:airflow@postgres/airflow
worker_concurrency = 16

[api]
auth_backends = airflow.api.auth.backend.basic_auth
```

---

## Quick Reference: What Each Component Reads/Writes

| Component | Reads | Writes |
|---|---|---|
| DAG Processor | `dags/` folder (Python files) | Serialized DAGs into Metadata DB |
| Scheduler | Serialized DAGs, task states | DAG runs, task state transitions |
| API Server | DAG runs, task states, logs metadata | Triggered DAG runs (via REST) |
| Worker | Task code (from dags/ folder) | Task state (success/fail), XComs, logs |
| Triggerer | Trigger records in DB | Task state (resume after defer) |

---

## Common Ports Summary

| Service | Default Port |
|---|---|
| API Server (UI + REST) | 8080 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| RabbitMQ management | 15672 |
| Flower (Celery monitor) | 5555 |
