# CeleryExecutor — Code Examples

> Apache Airflow 3. Full working examples for CeleryExecutor with Redis broker.

---

## 1. Full Docker Compose for Airflow 3 + CeleryExecutor

This is a production-ready Compose file with:
- PostgreSQL metadata DB
- Redis broker (with persistence)
- 2 Celery workers
- Flower monitoring UI
- Triggerer (for deferrable operators)

```yaml
# docker-compose.yaml
version: "3.8"

x-airflow-common:
  &airflow-common
  image: apache/airflow:3.0.0
  environment:
    &airflow-common-env
    AIRFLOW__CORE__EXECUTOR: CeleryExecutor
    AIRFLOW__CORE__PARALLELISM: "64"
    AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG: "32"
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CELERY__RESULT_BACKEND: db+postgresql://airflow:airflow@postgres/airflow
    AIRFLOW__CELERY__BROKER_URL: redis://redis:6379/0
    AIRFLOW__CELERY__WORKER_CONCURRENCY: "16"
    AIRFLOW__CELERY_BROKER_TRANSPORT_OPTIONS__VISIBILITY_TIMEOUT: "21600"
    AIRFLOW__CORE__FERNET_KEY: "81HqDtbqAywKSOumSha3BhWNOdQ26slT6K0YaZeZyPs="
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    AIRFLOW__WEBSERVER__SECRET_KEY: "replace-with-a-real-secret-in-production"
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
  # ── Infrastructure ──────────────────────────────────────────────────────────

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

  redis:
    image: redis:7-alpine
    # Enable AOF persistence so tasks are not lost on Redis restart
    command: redis-server --appendonly yes --appendfsync everysec
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 30s
      retries: 50
    restart: always

  # ── Airflow Services ─────────────────────────────────────────────────────────

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
      test: ["CMD-SHELL", 'airflow jobs check --job-type SchedulerJob --hostname "$(hostname)"']
      interval: 30s
      timeout: 10s
      retries: 5
    restart: always

  airflow-triggerer:
    <<: *airflow-common
    command: triggerer
    restart: always

  # ── Worker 1: Default queue ──────────────────────────────────────────────────
  airflow-worker-1:
    <<: *airflow-common
    command: celery worker --queues default
    environment:
      <<: *airflow-common-env
      AIRFLOW__CELERY__WORKER_CONCURRENCY: "16"
      DUMB_INIT_SETSID: "0"
    restart: always

  # ── Worker 2: Heavy tasks queue ──────────────────────────────────────────────
  airflow-worker-2:
    <<: *airflow-common
    command: celery worker --queues heavy_tasks
    environment:
      <<: *airflow-common-env
      AIRFLOW__CELERY__WORKER_CONCURRENCY: "4"  # Heavy tasks use more CPU per task
      DUMB_INIT_SETSID: "0"
    restart: always

  # ── Flower Monitoring ────────────────────────────────────────────────────────
  airflow-flower:
    <<: *airflow-common
    command: celery flower
    ports:
      - "5555:5555"
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:5555/"]
      interval: 30s
      timeout: 10s
      retries: 5
    restart: always

  # ── Init: DB migration + admin user ─────────────────────────────────────────
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
        echo "Airflow initialised successfully"
    environment:
      <<: *airflow-common-env

volumes:
  postgres-db-volume:
  redis-data:
```

---

## 2. Scaling Workers

```bash
# Scale workers up (same docker-compose.yaml, use the generic airflow-worker service)
docker compose up --scale airflow-worker=5 -d

# Check running services
docker compose ps

# Scale down to 2 workers
docker compose up --scale airflow-worker=2 -d

# View worker logs
docker compose logs -f airflow-worker
```

If you need named worker services (worker-1, worker-2 as above), you manage scaling by adding/removing service definitions. For anonymous scaling, use a single `airflow-worker` service without named variants.

---

## 3. Queue Assignment in a DAG

```python
# dags/queue_routing_demo.py

from airflow.decorators import dag, task
from datetime import datetime
import time


@dag(
    dag_id="queue_routing_demo",
    description="Demonstrates CeleryExecutor queue routing",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["executor", "celery"],
)
def queue_routing_demo():
    """
    This DAG demonstrates routing tasks to different Celery worker queues.

    Prerequisites:
    - Worker 1 started with: airflow celery worker --queues default
    - Worker 2 started with: airflow celery worker --queues heavy_tasks
    - Worker 3 started with: airflow celery worker --queues reporting
    """

    @task  # No queue = goes to the default queue
    def validate_input_data() -> dict:
        print("Validating data — runs on any default queue worker")
        time.sleep(1)
        return {"record_count": 150_000, "valid": True}

    @task(queue="heavy_tasks")  # Only runs on workers listening on heavy_tasks
    def run_heavy_transformation(validation_result: dict) -> str:
        print(f"Running heavy transform on {validation_result['record_count']:,} records")
        print("This task runs only on heavy_tasks queue workers (more CPU/RAM)")
        time.sleep(5)
        return "s3://my-bucket/output/2025-01-01/result.parquet"

    @task(queue="reporting")    # Only runs on workers listening on reporting
    def generate_report(output_path: str) -> None:
        print(f"Generating report from {output_path}")
        print("This task runs only on reporting queue workers")
        time.sleep(2)
        print("Report generated and emailed to stakeholders")

    validation = validate_input_data()
    output = run_heavy_transformation(validation)
    generate_report(output)


queue_routing_demo()
```

---

## 4. Setting `worker_concurrency` Per Worker Type

```bash
# Low-concurrency worker for CPU-heavy tasks (8-CPU machine)
airflow celery worker \
  --queues heavy_tasks \
  --concurrency 8

# High-concurrency worker for I/O-heavy tasks (e.g. HTTP calls, DB queries)
airflow celery worker \
  --queues api_tasks \
  --concurrency 32

# Default worker
airflow celery worker \
  --queues default \
  --concurrency 16
```

---

## 5. Verifying CeleryExecutor Is Working

```bash
# Confirm the executor is set
airflow config get-value core executor
# Expected: CeleryExecutor

# Check broker connectivity
airflow celery status

# Inspect queue depth in Redis
docker compose exec redis redis-cli LLEN default
# Returns the number of tasks waiting in the default queue

# List active workers via Flower API
curl http://localhost:5555/api/workers
```

---

## 6. Using Environment Variables Instead of `airflow.cfg`

For Docker/Kubernetes deployments, configure CeleryExecutor entirely via environment variables — no `airflow.cfg` editing needed:

```bash
# .env file (used by docker-compose)
AIRFLOW__CORE__EXECUTOR=CeleryExecutor
AIRFLOW__CORE__PARALLELISM=64
AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG=32
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@postgres/airflow
AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0
AIRFLOW__CELERY__RESULT_BACKEND=db+postgresql://airflow:airflow@postgres/airflow
AIRFLOW__CELERY__WORKER_CONCURRENCY=16
AIRFLOW__CELERY__OPERATION_TIMEOUT=1.0
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Prev Executor** | [01_LocalExecutor](../01_LocalExecutor/) |
| **Next Executor** | [03_KubernetesExecutor](../03_KubernetesExecutor/) |
| **Section Root** | [08_Executors](../) |
