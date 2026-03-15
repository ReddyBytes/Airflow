# Airflow 3 — Complete Docker Compose Setup

## Overview

This guide provides a complete, working Airflow 3 Docker Compose setup that you can use immediately. It includes all Airflow 3 components, environment configuration, common operations, and troubleshooting steps.

---

## Project Structure

```
airflow-docker/
├── docker-compose.yaml      # Main service definitions
├── .env                     # Environment variables
├── Dockerfile               # Custom image (for extra packages)
├── requirements.txt         # Extra Python packages
├── dags/                    # Your DAG files
├── logs/                    # Task logs (auto-created)
├── plugins/                 # Custom operators/hooks
└── config/                  # airflow.cfg overrides
```

---

## docker-compose.yaml

This is a complete, working Airflow 3 Docker Compose file with all components. Save this as `docker-compose.yaml` in your project root.

```yaml
# Airflow 3 — Complete Docker Compose Setup
# Includes: API Server, Scheduler, DAG Processor, Worker, Triggerer, Postgres, Redis

x-airflow-common:
  &airflow-common
  # Use this to build a custom image with extra packages:
  # build: .
  image: ${AIRFLOW_IMAGE_NAME:-apache/airflow:3.0.0}
  environment:
    &airflow-common-env
    AIRFLOW__CORE__EXECUTOR: CeleryExecutor
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CELERY__RESULT_BACKEND: db+postgresql://airflow:airflow@postgres/airflow
    AIRFLOW__CELERY__BROKER_URL: redis://:@redis:6379/0
    AIRFLOW__CORE__FERNET_KEY: ''
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: 'true'
    AIRFLOW__CORE__LOAD_EXAMPLES: 'true'
    AIRFLOW__API__AUTH_BACKENDS: 'airflow.api.auth.backend.basic_auth,airflow.api.auth.backend.session'
    AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK: 'true'
    # Optional: Set your timezone
    # AIRFLOW__CORE__DEFAULT_TIMEZONE: 'America/New_York'
    _PIP_ADDITIONAL_REQUIREMENTS: ${_PIP_ADDITIONAL_REQUIREMENTS:-}
  volumes:
    - ${AIRFLOW_PROJ_DIR:-.}/dags:/opt/airflow/dags
    - ${AIRFLOW_PROJ_DIR:-.}/logs:/opt/airflow/logs
    - ${AIRFLOW_PROJ_DIR:-.}/config:/opt/airflow/config
    - ${AIRFLOW_PROJ_DIR:-.}/plugins:/opt/airflow/plugins
  user: "${AIRFLOW_UID:-50000}:0"
  depends_on:
    &airflow-common-depends-on
    redis:
      condition: service_healthy
    postgres:
      condition: service_healthy

services:
  # ──────────────────────────────────────────────────────────────────────────
  # INFRASTRUCTURE
  # ──────────────────────────────────────────────────────────────────────────

  postgres:
    image: postgres:13
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - postgres-db-volume:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 10s
      retries: 5
      start_period: 5s
    restart: always

  redis:
    image: redis:7.2-bookworm
    expose:
      - 6379
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 30s
      retries: 50
      start_period: 30s
    restart: always

  # ──────────────────────────────────────────────────────────────────────────
  # AIRFLOW 3 CORE COMPONENTS
  # ──────────────────────────────────────────────────────────────────────────

  # NEW in Airflow 3: replaces 'airflow-webserver'
  # Serves both the Web UI and the REST API
  airflow-apiserver:
    <<: *airflow-common
    command: api-server
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    restart: always
    depends_on:
      <<: *airflow-common-depends-on
      airflow-init:
        condition: service_completed_successfully

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8974/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    restart: always
    depends_on:
      <<: *airflow-common-depends-on
      airflow-init:
        condition: service_completed_successfully

  # NEW in Airflow 3: standalone DAG Processor
  # In Airflow 2, this was embedded inside the Scheduler
  airflow-dag-processor:
    <<: *airflow-common
    command: dag-processor
    healthcheck:
      test: ["CMD-SHELL", 'airflow jobs check --job-type DagProcessorJob --hostname "$${HOSTNAME}"']
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    restart: always
    depends_on:
      <<: *airflow-common-depends-on
      airflow-init:
        condition: service_completed_successfully

  airflow-worker:
    <<: *airflow-common
    command: celery worker
    healthcheck:
      test:
        - "CMD-SHELL"
        - 'celery --app airflow.providers.celery.executors.celery_executor.app inspect ping -d "celery@$${HOSTNAME}" -t 10'
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    environment:
      <<: *airflow-common-env
      # Required for graceful shutdown on SIGINT
      DUMB_INIT_SETSID: "0"
    restart: always
    depends_on:
      <<: *airflow-common-depends-on
      airflow-init:
        condition: service_completed_successfully

  airflow-triggerer:
    <<: *airflow-common
    command: triggerer
    healthcheck:
      test: ["CMD-SHELL", 'airflow jobs check --job-type TriggererJob --hostname "$${HOSTNAME}"']
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    restart: always
    depends_on:
      <<: *airflow-common-depends-on
      airflow-init:
        condition: service_completed_successfully

  # ──────────────────────────────────────────────────────────────────────────
  # ONE-TIME INITIALIZATION (runs once, then exits)
  # ──────────────────────────────────────────────────────────────────────────

  airflow-init:
    <<: *airflow-common
    entrypoint: /bin/bash
    command:
      - -c
      - |
        mkdir -p /sources/logs /sources/dags /sources/plugins
        chown -R "${AIRFLOW_UID}:0" /sources/{logs,dags,plugins}
        exec /entrypoint airflow version
    environment:
      <<: *airflow-common-env
      _AIRFLOW_DB_MIGRATE: 'true'
      _AIRFLOW_WWW_USER_CREATE: 'true'
      _AIRFLOW_WWW_USER_USERNAME: ${_AIRFLOW_WWW_USER_USERNAME:-admin}
      _AIRFLOW_WWW_USER_PASSWORD: ${_AIRFLOW_WWW_USER_PASSWORD:-admin}
      _PIP_ADDITIONAL_REQUIREMENTS: ''
    user: "0:0"
    volumes:
      - ${AIRFLOW_PROJ_DIR:-.}:/sources

  # ──────────────────────────────────────────────────────────────────────────
  # OPTIONAL: Celery Flower (Worker monitoring dashboard)
  # ──────────────────────────────────────────────────────────────────────────

  flower:
    <<: *airflow-common
    command: celery flower
    profiles:
      - flower
    ports:
      - "5555:5555"
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:5555/"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    restart: always
    depends_on:
      <<: *airflow-common-depends-on
      airflow-init:
        condition: service_completed_successfully

volumes:
  postgres-db-volume:
```

---

## .env File Template

Create this as `.env` in your project root:

```bash
# Required: your local user ID (prevents file permission issues on Linux)
AIRFLOW_UID=50000

# Admin user credentials (used by airflow-init on first run)
_AIRFLOW_WWW_USER_USERNAME=admin
_AIRFLOW_WWW_USER_PASSWORD=admin

# Optional: Custom Airflow image tag
AIRFLOW_IMAGE_NAME=apache/airflow:3.0.0

# Optional: Extra pip packages to install at container startup
# (use custom Dockerfile for production instead)
_PIP_ADDITIONAL_REQUIREMENTS=

# Optional: Project directory override
# AIRFLOW_PROJ_DIR=/path/to/your/project
```

> **Security note:** Change `_AIRFLOW_WWW_USER_PASSWORD` before deploying to any shared or production environment. Never commit `.env` to version control if it contains real credentials.

---

## Custom Dockerfile (Adding Python Packages)

When you need extra Python packages in your Airflow environment, build a custom image:

```dockerfile
# Dockerfile
FROM apache/airflow:3.0.0

# Copy and install requirements
COPY requirements.txt /
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt
```

```
# requirements.txt
pandas==2.1.0
boto3==1.34.0
scikit-learn==1.3.0
psycopg2-binary==2.9.9
apache-airflow-providers-amazon==8.0.0
```

Update `docker-compose.yaml` to build your image:

```yaml
x-airflow-common:
  &airflow-common
  build: .          # ← change from 'image:' to 'build:'
  # image: ${AIRFLOW_IMAGE_NAME:-apache/airflow:3.0.0}   ← comment this out
```

Then rebuild:
```bash
docker compose build
docker compose up -d
```

---

## Common Operations

### Start / Stop

```bash
# Initialize (first time only)
docker compose up airflow-init

# Start all services in background
docker compose up -d

# Stop all services (keep data)
docker compose down

# Stop and delete all data (full reset)
docker compose down --volumes --remove-orphans
```

### Monitoring

```bash
# Check service health
docker compose ps

# View logs for all services
docker compose logs

# Follow a specific service's logs
docker compose logs -f airflow-dag-processor

# Check scheduler health
docker compose exec airflow-scheduler airflow jobs check --job-type SchedulerJob

# Check all jobs
docker compose exec airflow-apiserver airflow jobs check
```

### DAG Management

```bash
# List all DAGs
docker compose exec airflow-apiserver airflow dags list

# Trigger a DAG run
docker compose exec airflow-apiserver airflow dags trigger my_dag_id

# Unpause a DAG
docker compose exec airflow-apiserver airflow dags unpause my_dag_id

# Pause a DAG
docker compose exec airflow-apiserver airflow dags pause my_dag_id

# Delete a DAG and all its runs
docker compose exec airflow-apiserver airflow dags delete my_dag_id
```

### Database Operations

```bash
# Check database connectivity
docker compose exec airflow-apiserver airflow db check

# Apply schema migrations (after Airflow upgrade)
docker compose exec airflow-apiserver airflow db migrate

# Open a PostgreSQL shell
docker compose exec postgres psql -U airflow -d airflow
```

### User Management

```bash
# List users
docker compose exec airflow-apiserver airflow users list

# Create a new user
docker compose exec airflow-apiserver airflow users create \
  --username myuser --password mypassword \
  --firstname My --lastname User \
  --role Viewer --email myuser@example.com

# Reset a password
docker compose exec airflow-apiserver airflow users reset-password --username admin
```

---

## Troubleshooting

### Problem: Container exits immediately

```bash
# Check exit code and last logs
docker compose logs airflow-scheduler | tail -50
docker compose ps -a   # Shows exited containers with exit codes
```

**Common cause:** Database not ready yet. The health checks should prevent this, but on slow machines the startup timeout may need increasing:

```yaml
# In docker-compose.yaml, increase start_period:
healthcheck:
  start_period: 60s   # increase from 30s
```

### Problem: DAG not appearing in UI

```bash
# 1. Check DAG Processor logs for errors
docker compose logs airflow-dag-processor

# 2. Check for import errors via CLI
docker compose exec airflow-apiserver airflow dags list-import-errors

# 3. Test your DAG file manually
docker compose exec airflow-apiserver python /opt/airflow/dags/my_dag.py
```

### Problem: "ModuleNotFoundError" in task logs

The Python package is not installed in the Airflow container.

```bash
# Quick test (not for production):
docker compose exec airflow-worker pip install my-package

# Proper fix: add to requirements.txt and rebuild the image
echo "my-package==1.0.0" >> requirements.txt
docker compose build
docker compose up -d
```

### Problem: Tasks stuck in "queued" state

```bash
# Check if the worker is running and healthy
docker compose ps airflow-worker

# Check the worker's task queue
docker compose exec airflow-worker celery --app airflow.providers.celery.executors.celery_executor.app inspect active

# Check the broker (Redis) is reachable
docker compose exec airflow-worker celery --app airflow.providers.celery.executors.celery_executor.app inspect ping
```

### Problem: "Unable to connect to database" errors

```bash
# Verify PostgreSQL is running and healthy
docker compose ps postgres

# Test connection from Airflow container
docker compose exec airflow-apiserver airflow db check

# Verify the connection string in docker-compose.yaml:
# AIRFLOW__DATABASE__SQL_ALCHEMY_CONN should match postgres service credentials
```

### Problem: Port 8080 already in use

```yaml
# In docker-compose.yaml, change the host port:
airflow-apiserver:
  ports:
    - "8081:8080"   # Access UI at localhost:8081
```

### Problem: Logs folder permission denied

```bash
# Regenerate .env with correct UID
echo -e "AIRFLOW_UID=$(id -u)" > .env

# Full clean restart
docker compose down --volumes
docker compose up airflow-init
docker compose up -d
```

---

## LocalExecutor Setup (Simpler, No Redis/Workers)

If you want a simpler setup for learning without CeleryExecutor, use this minimal `docker-compose.yaml`:

```yaml
# Minimal Airflow 3 setup — LocalExecutor (no Redis, no separate workers)

x-airflow-common:
  &airflow-common
  image: apache/airflow:3.0.0
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CORE__FERNET_KEY: ''
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: 'true'
    AIRFLOW__CORE__LOAD_EXAMPLES: 'true'
  volumes:
    - ./dags:/opt/airflow/dags
    - ./logs:/opt/airflow/logs
    - ./plugins:/opt/airflow/plugins
  user: "${AIRFLOW_UID:-50000}:0"
  depends_on:
    postgres:
      condition: service_healthy

services:
  postgres:
    image: postgres:13
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - postgres-db-volume:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 10s
      retries: 5

  airflow-init:
    <<: *airflow-common
    command: version
    environment:
      _AIRFLOW_DB_MIGRATE: 'true'
      _AIRFLOW_WWW_USER_CREATE: 'true'
      _AIRFLOW_WWW_USER_USERNAME: admin
      _AIRFLOW_WWW_USER_PASSWORD: admin
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow

  airflow-apiserver:
    <<: *airflow-common
    command: api-server
    ports:
      - "8080:8080"
    depends_on:
      airflow-init:
        condition: service_completed_successfully

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
    depends_on:
      airflow-init:
        condition: service_completed_successfully

  airflow-dag-processor:
    <<: *airflow-common
    command: dag-processor
    depends_on:
      airflow-init:
        condition: service_completed_successfully

  airflow-triggerer:
    <<: *airflow-common
    command: triggerer
    depends_on:
      airflow-init:
        condition: service_completed_successfully

volumes:
  postgres-db-volume:
```

With LocalExecutor, tasks run as subprocesses on the same machine as the Scheduler. No Redis or separate Worker containers needed.
