# Airflow 3 Installation — Cheatsheet

## Install Commands (Airflow 3 Only)

```bash
# ─── Docker Compose Method (Recommended) ───────────────────────────────────

# 1. Download docker-compose.yaml
curl -LfO 'https://airflow.apache.org/docs/apache-airflow/3.0.0/docker-compose.yaml'

# 2. Create directories + set UID
mkdir -p ./dags ./logs ./plugins ./config
echo -e "AIRFLOW_UID=$(id -u)" > .env

# 3. Initialize database (run once)
docker compose up airflow-init

# 4. Start all services
docker compose up -d

# ─── pip Install Method ─────────────────────────────────────────────────────

# Install
AIRFLOW_VERSION=3.0.0
PYTHON_VERSION="$(python --version | cut -d " " -f 2 | cut -d "." -f 1-2)"
CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
pip install "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"

# Initialize DB (Airflow 3 uses 'migrate', not 'init')
airflow db migrate

# Create admin user
airflow users create --username admin --password admin \
  --firstname Admin --lastname User --role Admin --email admin@example.com
```

---

## Airflow 3 vs Airflow 2 — Command Changes

| Task | Airflow 2 Command | Airflow 3 Command |
|---|---|---|
| Start Web UI | `airflow webserver` | `airflow api-server` |
| Initialize database | `airflow db init` | `airflow db migrate` |
| Start DAG parsing | (embedded in scheduler) | `airflow dag-processor` |
| Apply schema upgrades | `airflow db upgrade` | `airflow db migrate` |

---

## Docker Compose Commands

```bash
# Start all services in background
docker compose up -d

# View service status
docker compose ps

# View logs for a specific service
docker compose logs airflow-apiserver
docker compose logs airflow-scheduler
docker compose logs airflow-dag-processor
docker compose logs airflow-worker

# Follow logs in real time
docker compose logs -f airflow-scheduler

# Stop all services (keep data)
docker compose down

# Stop and delete all data
docker compose down --volumes --remove-orphans

# Restart a single service
docker compose restart airflow-scheduler

# Run a command inside a container
docker compose exec airflow-apiserver airflow dags list
docker compose exec airflow-apiserver airflow db check
```

---

## Key Environment Variables

| Variable | Description | Example |
|---|---|---|
| `AIRFLOW_UID` | Linux user ID (prevents permission issues) | `50000` |
| `_AIRFLOW_WWW_USER_USERNAME` | Admin username for airflow-init | `admin` |
| `_AIRFLOW_WWW_USER_PASSWORD` | Admin password for airflow-init | `admin` |
| `AIRFLOW__CORE__EXECUTOR` | Executor type | `CeleryExecutor` |
| `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` | Database connection string | `postgresql+psycopg2://...` |
| `AIRFLOW__CELERY__BROKER_URL` | Redis/RabbitMQ URL | `redis://redis:6379/0` |
| `AIRFLOW__CELERY__RESULT_BACKEND` | Celery result backend | `db+postgresql://...` |
| `AIRFLOW__CORE__FERNET_KEY` | Encryption key for stored secrets | (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) |

---

## Ports Reference

| Service | Default Port | Purpose |
|---|---|---|
| API Server | 8080 | Web UI + REST API |
| PostgreSQL | 5432 | Metadata Database |
| Redis | 6379 | Message Broker |
| Flower | 5555 | Celery worker monitor (optional) |

---

## Docker Compose Services (Airflow 3)

| Service | Role | Note |
|---|---|---|
| `airflow-apiserver` | Web UI + REST API | Replaces `airflow-webserver` from Airflow 2 |
| `airflow-scheduler` | Task scheduling | No longer parses DAGs in v3 |
| `airflow-dag-processor` | DAG file parsing | NEW — did not exist as separate service in v2 |
| `airflow-worker` | Task execution | CeleryExecutor workers |
| `airflow-triggerer` | Deferrable operators | Async event loop |
| `airflow-init` | One-time setup | Runs `db migrate` + creates admin user, then exits |
| `postgres` | Metadata database | PostgreSQL |
| `redis` | Message broker | For CeleryExecutor |

---

## Folder Structure

```
project/
├── dags/        ← Put your DAG .py files here
├── logs/        ← Task logs written here automatically
├── plugins/     ← Custom operators, hooks, sensors
├── config/      ← airflow.cfg overrides
├── .env         ← AIRFLOW_UID and other env vars
└── docker-compose.yaml
```

---

## First-Run Checklist

- [ ] Docker and Docker Compose V2 installed
- [ ] At least 4 GB RAM available
- [ ] `./dags`, `./logs`, `./plugins`, `./config` directories created
- [ ] `.env` file with `AIRFLOW_UID=$(id -u)` created
- [ ] `docker compose up airflow-init` completed successfully
- [ ] `docker compose up -d` started all services
- [ ] `docker compose ps` shows all services healthy
- [ ] http://localhost:8080 accessible
- [ ] Login with admin / admin works
- [ ] Default example DAGs visible in UI

---

## Adding Python Packages

```bash
# Option 1: Use --build-arg with custom image
# Create requirements.txt
echo "pandas==2.0.0" >> requirements.txt
echo "boto3" >> requirements.txt

# Create a custom Dockerfile
cat > Dockerfile << 'EOF'
FROM apache/airflow:3.0.0
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EOF

# Update docker-compose.yaml to build your image:
# image: ${AIRFLOW_IMAGE_NAME:-apache/airflow:3.0.0}
# becomes:
# build: .

docker compose build
docker compose up -d
```

---

## Useful Airflow 3 CLI Commands

```bash
# List all DAGs
airflow dags list

# Trigger a DAG run manually
airflow dags trigger my_dag_id

# List task instances for a DAG run
airflow tasks list my_dag_id

# Check database connectivity
airflow db check

# Validate a DAG file
airflow dags show my_dag_id

# List all connections
airflow connections list

# Add a connection
airflow connections add my_conn --conn-type postgres --conn-host localhost
```
