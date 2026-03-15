# LocalExecutor — Cheatsheet

> Quick reference for Apache Airflow 3. Single-machine parallel execution, no broker required.

---

## Core Configuration

```ini
# airflow.cfg
[core]
executor = LocalExecutor

# Total concurrent tasks across all DAGs
parallelism = 32

# Max tasks running at once per individual DAG
max_active_tasks_per_dag = 16

# Max concurrent DAG runs per DAG
max_active_runs_per_dag = 8
```

```bash
# Environment variables (override airflow.cfg)
export AIRFLOW__CORE__EXECUTOR=LocalExecutor
export AIRFLOW__CORE__PARALLELISM=32
export AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG=16
export AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG=8
```

---

## Key Configuration Parameters

| Config Key | Env Var | Default | Description |
|---|---|---|---|
| `[core] executor` | `AIRFLOW__CORE__EXECUTOR` | `SequentialExecutor` | Set to `LocalExecutor` |
| `[core] parallelism` | `AIRFLOW__CORE__PARALLELISM` | `32` | Max total concurrent tasks across all DAGs |
| `[core] max_active_tasks_per_dag` | `AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG` | `16` | Max concurrent tasks per single DAG |
| `[core] max_active_runs_per_dag` | `AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG` | `16` | Max concurrent DAG runs per DAG |
| `[core] sql_alchemy_conn` | `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` | SQLite | **Must** be PostgreSQL or MySQL |

---

## Docker Compose Snippet

```yaml
# docker-compose.yaml — LocalExecutor setup
version: "3.8"

x-airflow-common: &airflow-common
  image: apache/airflow:3.0.0
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__CORE__PARALLELISM: "32"
    AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG: "16"
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CORE__FERNET_KEY: ""
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
  volumes:
    - ./dags:/opt/airflow/dags
    - ./logs:/opt/airflow/logs
  depends_on:
    postgres:
      condition: service_healthy

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 5s
      retries: 5

  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler

  airflow-init:
    <<: *airflow-common
    command: version
    environment:
      _AIRFLOW_DB_MIGRATE: "true"
      _AIRFLOW_WWW_USER_CREATE: "true"
      _AIRFLOW_WWW_USER_USERNAME: admin
      _AIRFLOW_WWW_USER_PASSWORD: admin
```

> Note: With LocalExecutor, there is **no separate worker service** — the scheduler forks subprocesses directly.

---

## Sizing Guide

| Machine CPUs | Recommended `parallelism` | Recommended `max_active_tasks_per_dag` |
|---|---|---|
| 2 | 4–6 | 4 |
| 4 | 8–12 | 8 |
| 8 | 16–24 | 12 |
| 16 | 32–48 | 16 |
| 32 | 64–96 | 32 |

Rule of thumb: `parallelism` = 2–3× CPU count. Leave headroom for the scheduler itself.

---

## When to Use LocalExecutor

| Condition | Use LocalExecutor? |
|---|---|
| Single Airflow machine | Yes |
| Development / staging | Yes |
| ≤ ~50 concurrent tasks | Yes |
| Need simplicity, no broker | Yes |
| Multi-node worker fleet needed | No — use CeleryExecutor |
| > 100 concurrent tasks regularly | No — use CeleryExecutor |
| Need per-task container isolation | No — use KubernetesExecutor |
| Already on Kubernetes | No — use KubernetesExecutor |

---

## Quick Comparison

| Feature | SequentialExecutor | LocalExecutor | CeleryExecutor |
|---|---|---|---|
| Parallelism | 1 task | Many (subprocess per task) | Many (distributed workers) |
| Requires PostgreSQL | No (SQLite OK) | **Yes** | Yes |
| Requires broker | No | No | Yes (Redis/RabbitMQ) |
| Multi-machine | No | No | Yes |
| Setup complexity | Zero | Low | Medium-High |

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Next Executor** | [02_CeleryExecutor](../02_CeleryExecutor/) |
| **Section Root** | [08_Executors](../) |
