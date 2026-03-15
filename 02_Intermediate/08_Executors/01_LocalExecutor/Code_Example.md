# LocalExecutor — Code Examples

> Apache Airflow 3. All examples assume PostgreSQL as the metadata database.

---

## 1. Minimal `airflow.cfg` for LocalExecutor

```ini
# airflow.cfg — minimal LocalExecutor production config

[core]
executor = LocalExecutor
parallelism = 24
max_active_tasks_per_dag = 12
max_active_runs_per_dag = 4

[database]
sql_alchemy_conn = postgresql+psycopg2://airflow:airflow@localhost:5432/airflow

[logging]
base_log_folder = /opt/airflow/logs
```

---

## 2. Docker Compose for LocalExecutor (Airflow 3)

A minimal but production-ready Compose file. No Celery, no Redis — just PostgreSQL + scheduler + webserver.

```yaml
# docker-compose.yaml
version: "3.8"

x-airflow-common:
  &airflow-common
  image: apache/airflow:3.0.0
  environment:
    &airflow-common-env
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__CORE__PARALLELISM: "24"
    AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG: "12"
    AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG: "4"
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CORE__FERNET_KEY: "81HqDtbqAywKSOumSha3BhWNOdQ26slT6K0YaZeZyPs="
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    AIRFLOW__WEBSERVER__SECRET_KEY: "a-very-secret-key"
  volumes:
    - ./dags:/opt/airflow/dags
    - ./logs:/opt/airflow/logs
    - ./plugins:/opt/airflow/plugins
  depends_on:
    &airflow-common-depends-on
    postgres:
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
      timeout: 5s
      retries: 5
    restart: always

  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 5
    restart: always

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
    healthcheck:
      test: ["CMD", "airflow", "jobs", "check", "--job-type", "SchedulerJob", "--hostname", "$(hostname)"]
      interval: 30s
      timeout: 10s
      retries: 5
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
          --username admin \
          --firstname Admin \
          --lastname User \
          --role Admin \
          --email admin@example.com \
          --password admin
    environment:
      <<: *airflow-common-env

volumes:
  postgres-db-volume:
```

---

## 3. Setting Parallelism — Tuning for Your Machine

```python
# This is not Python code — it is a reference for airflow.cfg tuning.
#
# Machine:  4 CPU cores, 16 GB RAM
# Rule:     parallelism = 2-3× CPUs, leave slack for scheduler overhead
#
# [core]
# parallelism = 10          # 4 CPUs × 2.5 = 10 concurrent tasks
# max_active_tasks_per_dag = 6   # Half of parallelism — fair across DAGs
# max_active_runs_per_dag = 3
#
# Machine:  8 CPU cores, 32 GB RAM
# [core]
# parallelism = 20
# max_active_tasks_per_dag = 12
# max_active_runs_per_dag = 6
#
# Machine:  16 CPU cores, 64 GB RAM
# [core]
# parallelism = 40
# max_active_tasks_per_dag = 20
# max_active_runs_per_dag = 8
```

---

## 4. Sample DAG That Demonstrates Parallel Execution

This DAG has 5 independent extract tasks running in parallel, followed by a single transform step.

```python
# dags/parallel_etl_demo.py

from airflow.decorators import dag, task
from datetime import datetime
import time
import random

SOURCES = ["sales", "inventory", "customers", "orders", "returns"]


@dag(
    dag_id="parallel_etl_demo",
    description="Demonstrates LocalExecutor parallel task execution",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_tasks=len(SOURCES) + 1,  # Allow all extracts + transform to run
    tags=["demo", "executor"],
)
def parallel_etl_demo():
    """
    With LocalExecutor, all extract_* tasks below run simultaneously.
    With SequentialExecutor, they would run one after another.
    On a 4-CPU machine, the difference is ~5x faster.
    """

    @task
    def extract(source: str, **context) -> dict:
        """Simulate an extract that takes a variable amount of time."""
        duration = random.uniform(2, 8)
        print(f"Extracting from {source} — will take {duration:.1f}s")
        time.sleep(duration)
        row_count = random.randint(1000, 50000)
        print(f"Extracted {row_count:,} rows from {source}")
        return {"source": source, "rows": row_count, "date": context["ds"]}

    @task
    def transform_and_load(results: list) -> str:
        """Runs after all extracts complete. Receives a list of dicts via XCom."""
        total_rows = sum(r["rows"] for r in results)
        print(f"Transforming and loading {total_rows:,} total rows from {len(results)} sources")
        time.sleep(2)
        return f"Loaded {total_rows:,} rows successfully"

    @task
    def notify(summary: str) -> None:
        print(f"Pipeline complete: {summary}")

    # All extract tasks are independent — LocalExecutor runs them all at once
    extract_results = [extract.override(task_id=f"extract_{src}")(source=src) for src in SOURCES]

    # transform_and_load waits for all extracts to finish
    summary = transform_and_load(extract_results)
    notify(summary)


parallel_etl_demo()
```

---

## 5. Per-DAG Parallelism Override

You can override global parallelism limits on a per-DAG basis:

```python
from airflow.decorators import dag, task
from datetime import datetime


@dag(
    dag_id="high_parallelism_dag",
    schedule="@hourly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    # Allow this specific DAG to run more tasks at once than the global default
    max_active_tasks=32,
    max_active_runs=2,
)
def high_parallelism_dag():
    @task
    def process_partition(partition_id: int) -> int:
        import time
        time.sleep(1)
        return partition_id * 2

    results = process_partition.expand(partition_id=list(range(20)))
    return results


high_parallelism_dag()
```

---

## 6. Verifying LocalExecutor Is Active

```bash
# Check which executor Airflow is using
airflow config get-value core executor
# Expected output: LocalExecutor

# Or check via environment variable inspection
python -c "from airflow.configuration import conf; print(conf.get('core', 'executor'))"

# In Docker Compose:
docker compose exec airflow-scheduler airflow config get-value core executor
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Next Executor** | [02_CeleryExecutor](../02_CeleryExecutor/) |
| **Section Root** | [08_Executors](../) |
