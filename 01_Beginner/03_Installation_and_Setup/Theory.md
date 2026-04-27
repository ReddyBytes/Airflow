# Installing and Setting Up Airflow 3

## 📂 Navigation
⬅️ **Prev:** [Airflow 3 Architecture](../02_Airflow_3_Architecture/Theory.md) | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [Your First DAG](../04_Your_First_DAG/Theory.md)

---

## 📌 Learning Priority

**Must Learn** — core concepts, needed to understand the rest of this file:
[Docker Compose Install](#method-1--docker-compose-recommended) · [Step-by-Step Setup](#step-by-step-docker-compose-installation) · [Folder Structure](#folder-structure-after-setup)

**Should Learn** — important for real projects and interviews:
[Prerequisites](#prerequisites) · [pip Install](#method-2--pip-install-bare-metal) · [Common First-Run Issues](#common-first-run-issues)

**Good to Know** — useful in specific situations, not needed daily:
[First Login and UI Tour](#first-login-and-ui-tour) · [Airflow 3 Services](#airflow-3-services-in-docker-compose)

**Reference** — skim once, look up when needed:
[Stopping and Cleaning Up](#stopping-and-cleaning-up)

---

## The Restaurant Opening Analogy

Setting up Airflow 3 is like opening a new restaurant. You need the right kitchen equipment before the first order comes in.

- **Docker and Docker Compose** are your kitchen building and appliances — the infrastructure that makes everything else possible.
- **docker-compose.yaml** is your restaurant layout plan — it describes exactly which stations you need (grill, prep, cold storage) and how they connect.
- **`docker compose up airflow-init`** is the health and safety inspection before opening day — it sets up the database, creates the default admin user, and checks that all the wiring is correct.
- **`docker compose up -d`** is opening day — everything starts running and you're ready to take orders.
- **localhost:8080** is the front door — walk in and you'll see the entire operation.

The key difference from Airflow 2: in Airflow 3, the restaurant has more separate stations. The Recipe Department (DAG Processor) is its own room. The Manager's Dashboard (API Server) replaced the old notice board. Everything is more organized.

---

## Prerequisites

Before installing Airflow 3, make sure you have:

| Requirement | Minimum Version | Check Command |
|---|---|---|
| Python | 3.8+ | `python --version` |
| Docker | 20.10+ | `docker --version` |
| Docker Compose | 2.0+ (V2) | `docker compose version` |
| RAM | 4 GB minimum (8 GB recommended) | |
| Disk space | 10 GB free | |
| OS | Linux, macOS, or Windows WSL2 | |

> **Note:** Docker Compose V2 uses `docker compose` (no hyphen). If you are still on V1, you use `docker-compose`. All commands in this guide use V2 syntax.

---

## Method 1 — Docker Compose (Recommended)

Docker Compose is the recommended way to run Airflow 3, especially for learning and development. It handles all the component wiring for you.

### Airflow 3 Services in Docker Compose

Airflow 3's Docker Compose setup includes these services — note how they differ from Airflow 2:

| Service Name | What It Is | Airflow 2 Equivalent |
|---|---|---|
| `airflow-apiserver` | API Server (UI + REST API) | `airflow-webserver` (replaced!) |
| `airflow-scheduler` | Scheduler | `airflow-scheduler` |
| `airflow-dag-processor` | DAG Processor | (was inside scheduler — new standalone service) |
| `airflow-worker` | Celery Worker | `airflow-worker` |
| `airflow-triggerer` | Triggerer | `airflow-triggerer` |
| `postgres` | Metadata Database | `postgres` |
| `redis` | Message Broker (CeleryExecutor) | `redis` |

### Service Dependency Diagram

```mermaid
flowchart TB
    subgraph Infrastructure["Infrastructure (starts first)"]
        PG["postgres\n:5432"]
        Redis["redis\n:6379"]
    end

    subgraph AirflowCore["Airflow Core (starts after infra is healthy)"]
        Init["airflow-init\n(runs once, then exits)"]
        APIServer["airflow-apiserver\n:8080"]
        Scheduler["airflow-scheduler"]
        DAGProc["airflow-dag-processor"]
        Worker["airflow-worker"]
        Triggerer["airflow-triggerer"]
    end

    PG -->|healthy| Init
    Redis -->|healthy| Init
    Init -->|complete| APIServer
    Init -->|complete| Scheduler
    Init -->|complete| DAGProc
    Init -->|complete| Worker
    Init -->|complete| Triggerer
    PG --> APIServer
    PG --> Scheduler
    PG --> DAGProc
    PG --> Worker
    Redis --> Worker
    Redis --> Scheduler
```

### Step-by-Step Docker Compose Installation

**Step 1: Create a project directory**

```bash
mkdir airflow-project
cd airflow-project
```

**Step 2: Download the official Airflow 3 docker-compose.yaml**

```bash
curl -LfO 'https://airflow.apache.org/docs/apache-airflow/3.0.0/docker-compose.yaml'
```

**Step 3: Create required directories and set the AIRFLOW_UID**

```bash
mkdir -p ./dags ./logs ./plugins ./config

# Set AIRFLOW_UID to your user ID (important on Linux to avoid permission issues)
echo -e "AIRFLOW_UID=$(id -u)" > .env
```

**Step 4: Initialize the database and create the admin user**

```bash
docker compose up airflow-init
```

This command:
- Starts PostgreSQL and Redis.
- Runs `airflow db migrate` to create all database tables.
- Creates the default admin user (username: `admin`, password: `admin`).
- Exits when done (it is a one-time setup task).

You should see this at the end:
```
airflow-init_1  | Admin user admin created
airflow-init_1  | 3.0.0
airflow-project_airflow-init_1 exited with code 0
```

**Step 5: Start all Airflow services**

```bash
docker compose up -d
```

The `-d` flag runs in detached mode (background). All services start up.

**Step 6: Verify all services are healthy**

```bash
docker compose ps
```

You should see all services in `healthy` or `running` state. This may take 1-2 minutes on first start.

**Step 7: Open the Airflow UI**

Open your browser and go to: **http://localhost:8080**

Login with:
- Username: `admin`
- Password: `admin`

---

## Method 2 — pip Install (Bare Metal)

Use this method when you need Airflow running directly on a machine without Docker — for example, on a virtual machine or a CI runner.

### Installation

```bash
# Set your desired Airflow version and Python version
AIRFLOW_VERSION=3.0.0
PYTHON_VERSION="$(python --version | cut -d " " -f 2 | cut -d "." -f 1-2)"

# Generate the constraint URL for your versions
CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

# Install Airflow with constraints (constraints ensure compatible dependency versions)
pip install "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"
```

### Initialize the Database

In Airflow 3, the initialization command is `db migrate` — not `db init` which was used in Airflow 2:

```bash
# Set the database connection (use PostgreSQL for anything real)
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@localhost/airflow

# Run the migration (creates all tables, applies schema changes)
airflow db migrate
```

### Create an Admin User

```bash
airflow users create \
  --username admin \
  --password admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com
```

### Start Each Component

In Airflow 3, you start each component as a **separate process**. This is different from Airflow 2 where `airflow webserver` served the UI and DAG parsing was embedded in the Scheduler.

```bash
# Terminal 1 — API Server (replaces 'airflow webserver' from Airflow 2)
airflow api-server --port 8080

# Terminal 2 — Scheduler
airflow scheduler

# Terminal 3 — DAG Processor (NEW: separate process in Airflow 3)
airflow dag-processor

# Terminal 4 — Triggerer (if using deferrable operators)
airflow triggerer

# Terminal 5 — Worker (only if using CeleryExecutor)
airflow celery worker
```

> **Key Airflow 3 Change:** `airflow webserver` is replaced by `airflow api-server`. Running `airflow webserver` in Airflow 3 will fail.

---

## Folder Structure After Setup

```
airflow-project/
├── dags/                    # Your DAG Python files go here
│   └── example_dag.py
├── logs/                    # Task execution logs (created automatically)
│   └── dag_id=my_dag/
│       └── run_id=.../
│           └── task_id=.../
│               └── attempt=1.log
├── plugins/                 # Custom operators, hooks, and sensors
│   └── my_custom_operator.py
├── config/                  # airflow.cfg overrides
│   └── airflow.cfg
├── docker-compose.yaml      # Service definitions
└── .env                     # Environment variables (AIRFLOW_UID, passwords)
```

### Where to Put Your DAGs

Simply save your Python DAG files in the `dags/` folder. The DAG Processor automatically detects new files:

```bash
# Copy a DAG file into the folder
cp my_new_pipeline.py ./dags/

# The DAG Processor picks it up within ~30 seconds
# (depends on min_file_process_interval config)
```

---

## First Login and UI Tour

### Logging In

1. Open **http://localhost:8080**.
2. Enter `admin` / `admin` (default credentials set by `airflow-init`).
3. You will land on the **DAGs List** page.

### Key UI Pages

**DAGs List (Home Page)**
- Shows all your DAGs with their last run status.
- Toggle the on/off switch to pause or unpause a DAG.
- Filter by tag, state, or search by name.

**Grid View** (click a DAG name → "Grid")
- Shows all DAG runs as columns, tasks as rows.
- Color-coded by state: green = success, red = failed, yellow = running.
- Click any cell to see that specific task instance's details and logs.

**Graph View** (click a DAG name → "Graph")
- Shows the DAG's task dependency structure visually.
- Click a task node to see its status, logs, and XCom values.

**Logs** (click any task instance → "Logs" tab)
- Shows the full stdout/stderr from task execution.
- In Docker Compose, logs are also written to the `./logs/` folder on your machine.

### Changing the Default Password

```bash
# Via Docker Compose
docker compose exec airflow-apiserver airflow users reset-password --username admin

# Via pip install (bare metal)
airflow users reset-password --username admin
```

---

## Common First-Run Issues

### Issue: Services show as unhealthy in `docker compose ps`

**Cause:** Usually insufficient RAM, or services starting too slowly.

**Fix:**
```bash
# Check logs for the unhealthy container
docker compose logs airflow-scheduler

# If it says "Cannot connect to database", give it more time
# First start downloads ~1GB of images
```

### Issue: No DAGs appearing in the UI

**Cause:** DAG Processor hasn't completed a parse cycle, or the DAG file has an error.

**Fix:**
```bash
# Check DAG Processor logs for errors
docker compose logs airflow-dag-processor

# Also check: UI → Browse → Import Errors
```

### Issue: Permission denied errors on logs/ or dags/ folders

**Cause:** AIRFLOW_UID in .env doesn't match your local user ID.

**Fix:**
```bash
# Regenerate .env with correct UID
echo -e "AIRFLOW_UID=$(id -u)" > .env

# Full restart with clean volumes
docker compose down -v
docker compose up airflow-init
docker compose up -d
```

### Issue: Port 8080 is already in use

**Fix:**
```bash
# Find what's using port 8080
lsof -i :8080

# Change the host port in docker-compose.yaml:
# ports:
#   - "8081:8080"   ← access UI at localhost:8081 instead
```

---

## Stopping and Cleaning Up

```bash
# Stop all containers (keeps your data and database)
docker compose down

# Stop and delete all data (clean slate)
docker compose down --volumes --remove-orphans

# Full cleanup including downloaded images
docker compose down --volumes --rmi all
```

---

## 📂 Navigation
⬅️ **Prev:** [Airflow 3 Architecture](../02_Airflow_3_Architecture/Theory.md) | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [Your First DAG](../04_Your_First_DAG/Theory.md)
