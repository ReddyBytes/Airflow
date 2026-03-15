# What's New in Airflow 3 — Interview Q&A

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Asset-Driven Scheduling](../31_Asset_Driven_Scheduling/Theory.md)**

---

## Q1: What is the API Server in Airflow 3, and how does it differ from the old Webserver?

In Airflow 2 there was a single `webserver` process that served both the web UI and the REST API. Airflow 3 replaces it with the **API Server** (`airflow api-server`), which serves the new React-based UI and the REST API at `/api/v2/`.

The key differences:

| | Airflow 2 Webserver | Airflow 3 API Server |
|--|---------------------|----------------------|
| Command | `airflow webserver` | `airflow api-server` |
| REST API path | `/api/v1/` | `/api/v2/` |
| UI framework | Jinja2 + jQuery | React (SPA) |
| DB access | Direct | Via Internal API only |
| Auth | FAB hardcoded | Pluggable Auth Manager |

The biggest architectural shift: the API Server no longer touches the metadata database directly. All state reads and writes go through the **Internal API**, meaning the UI tier is fully decoupled from the data tier. This makes horizontal scaling of the API Server straightforward.

---

## Q2: What is the DAG Processor and why is it now a separate component?

In Airflow 2, the Scheduler was responsible for both scheduling task runs and parsing DAG files. If a badly written DAG caused a parsing crash, it could take down the Scheduler entirely.

In Airflow 3, **DAG parsing is moved to a standalone `dag-processor` process**. The Scheduler reads already-parsed DAG definitions from the database via the Internal API; it no longer touches DAG files at all.

Benefits:
- A broken DAG cannot crash the Scheduler
- The DAG Processor can be scaled independently from the Scheduler
- DAG parsing can run on a node without access to the broker or executor
- Crash loops in parsing are isolated and visible in the DAG Processor's own logs

The `dag-processor` is a **required component** in Airflow 3. If you omit it from your deployment, no DAGs will be parsed and none will run.

```bash
# Start the DAG Processor
airflow dag-processor

# In Docker Compose
dag-processor:
  image: apache/airflow:3.0.0
  command: dag-processor
  volumes:
    - ./dags:/opt/airflow/dags
```

---

## Q3: What is the Internal API and why does it matter?

The Internal API is an HTTP-based interface through which all Airflow components communicate instead of sharing a direct database connection.

In Airflow 2, the Scheduler, Workers, and Webserver all connected directly to the metadata database (Postgres/MySQL). This meant:
- Every component needed DB credentials
- Network firewall rules were complex
- DB connection pool exhaustion was a common scaling problem

In Airflow 3, only the **API Server** (and the Scheduler itself for writes) touches the DB. All other components call the Internal API over HTTP.

```
Airflow 2:  Scheduler → DB ← Webserver ← Workers
Airflow 3:  Scheduler → DB ← API Server ← (Internal API) ← Workers, UI
```

This dramatically reduces the number of DB connections in a large deployment and makes it easier to run workers in isolated network segments.

---

## Q4: What happened to Datasets in Airflow 3?

Datasets were **renamed to Assets** in Airflow 3. The concept is identical — a logical reference to a data artifact, identified by a URI — but Assets come with significant enhancements:

| Feature | Datasets (v2) | Assets (v3) |
|---------|--------------|-------------|
| Class name | `Dataset` | `Asset` |
| Import | `from airflow.datasets import Dataset` | `from airflow.sdk import Asset` |
| `@asset` decorator | No | Yes |
| OR logic | No | `AssetAny` |
| AND logic | Implicit only | `AssetAll` (explicit) |
| Aliases | No | `AssetAlias` |
| Groups | No | `group=` param |

The URI is preserved, so existing DAG run history is not broken when you rename from `Dataset` to `Asset`.

---

## Q5: What is DAG Versioning in Airflow 3?

DAG Versioning means that Airflow 3 **stores a snapshot of each DAG's structure** every time the DAG file changes. When you look at a historical DAG run in the UI, you see the task graph as it existed at the time of that run — not today's current version.

Before versioning, if you added or removed tasks from a DAG, old runs in the UI would show the current task graph superimposed over historical data, causing confusing mismatches.

With versioning:
- Each DAG file change creates a new version record
- Runs are associated with the version active when they were scheduled
- You can browse version history in the UI
- Old versions can be re-run (they run against the stored version, not the current code)

---

## Q6: How does the Auth Manager work in Airflow 3, and what replaces FAB?

In Airflow 2, Flask-AppBuilder (FAB) was the hardcoded authentication and authorization framework. Airflow 3 introduces a **pluggable Auth Manager** interface — an abstract class that any implementation can satisfy.

Two shipped implementations:

1. **SimpleAuthManager** — username/password from config file. Designed for local development and CI. Not for production.
2. **FabAuthManager** — the FAB-based auth from Airflow 2, now packaged in `apache-airflow-providers-fab`. This is the default production auth manager.

Configuration:
```ini
[core]
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager
# OR for dev:
auth_manager = airflow.auth.managers.simple.SimpleAuthManager
```

You can also write a **custom Auth Manager** by subclassing `BaseAuthManager` and implementing the required methods, enabling SSO, LDAP, or any identity provider without patching Airflow itself.

---

## Q7: What is the Edge Executor?

The **Edge Executor** is a new executor type in Airflow 3 that lets you run tasks on **lightweight remote worker nodes** that communicate with the Airflow API Server over HTTP — no direct database connection, no message broker required.

Key differences from CeleryExecutor:

| | CeleryExecutor | EdgeExecutor |
|--|---------------|--------------|
| Transport | Redis/RabbitMQ broker | HTTP to API Server |
| Worker needs DB? | No (broker only) | No |
| Worker needs broker? | Yes | No |
| Ideal for | Cloud VMs, containers | IoT devices, edge nodes, remote sites |
| Worker startup | `celery worker` | `airflow edge worker` |

Edge workers **poll** the API Server for tasks. This makes them deployable behind NAT, in isolated networks, or on edge devices that cannot receive inbound connections.

---

## Q8: What are the most important breaking changes when migrating from Airflow 2 to Airflow 3?

The breaking changes that affect the most users:

1. **`airflow webserver` removed** — replaced by `airflow api-server`
2. **`airflow db init` removed** — use `airflow db migrate`
3. **`SubDagOperator` removed** — migrate to `TaskGroup`
4. **`Dataset` renamed to `Asset`** — update all imports
5. **`provide_context=True` removed** — context is always provided to `PythonOperator`
6. **`execution_date` → `logical_date`** — update all `context["execution_date"]` references
7. **REST API at `/api/v2/`** — clients pointed at `/api/v1/` will get 404
8. **FAB no longer default auth** — must explicitly set `auth_manager` in config
9. **`dag-processor` required** — deployments without it will have no DAGs

---

## Q9: What are the migration steps from Airflow 2 to Airflow 3?

A safe migration path:

**Step 1 — Upgrade the metadata DB:**
```bash
pip install apache-airflow==3.0.0
airflow db migrate
```

**Step 2 — Update DAG code:**
```python
# Replace all Dataset imports
from airflow.sdk import Asset  # was: from airflow.datasets import Dataset

# Remove provide_context=True
# Before:
PythonOperator(task_id="t", python_callable=fn, provide_context=True)
# After:
PythonOperator(task_id="t", python_callable=fn)

# Update context keys
context["logical_date"]  # was: context["execution_date"]
```

**Step 3 — Update deployment:**
```yaml
# docker-compose.yml — replace webserver with api-server, add dag-processor
services:
  api-server:
    command: api-server    # was: webserver
  dag-processor:
    command: dag-processor  # new required service
```

**Step 4 — Update config:**
```ini
[api_server]             # was: [webserver]
base_url = http://localhost:8080

[core]
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager
```

**Step 5 — Update REST API clients:**
Change all calls from `/api/v1/` to `/api/v2/`.

---

## Q10: How does the new React UI in Airflow 3 differ from the Airflow 2 UI?

The Airflow 3 UI is a complete rewrite as a **React single-page application (SPA)** served by the API Server. The Airflow 2 UI was rendered server-side using Jinja2 templates.

Key UX improvements:
- **Grid view is the default** — shows a run/task matrix replacing the old Tree view
- **Graph view** shows the current task graph with run status overlaid
- **Assets page** — dedicated view for browsing assets, their lineage, and update history
- **DAG Versioning UI** — version history tab on each DAG page
- **Faster navigation** — SPA architecture means page transitions are instant
- **Runs detail** — task logs open in the same page without full reload

The REST API powers all UI operations, which means the UI and the API are always in sync — no separate code paths.

---

## Q11: What happened to `airflow db init` and why was it removed?

`airflow db init` was an Airflow 2 command that created the metadata database schema from scratch. It had a confusing dual role: it was used both for initial setup and (incorrectly) as an upgrade command.

In Airflow 3, `airflow db init` is removed. The replacement is `airflow db migrate`, which:
- Creates the schema on a fresh database (same as old `db init`)
- Applies incremental Alembic migrations on an existing database (same as old `db upgrade`)
- Is safe to run on every deployment — it is idempotent

```bash
# Airflow 2
airflow db init       # first-time setup
airflow db upgrade    # after upgrading Airflow version

# Airflow 3 — one command for both
airflow db migrate
```

---

## Q12: What is an ObjectStoragePath and why was it introduced?

`ObjectStoragePath` is a new Airflow 3 API that provides a **unified file system interface** for S3, GCS, Azure Blob Storage, and local file systems — modelled after Python's `pathlib.Path`.

Before Airflow 3, reading and writing files in DAGs required provider-specific code:
```python
# S3 — boto3
s3 = boto3.client("s3")
s3.get_object(Bucket="my-bucket", Key="file.csv")

# GCS — google-cloud-storage
storage.Client().bucket("my-bucket").blob("file.csv").download_as_bytes()
```

With `ObjectStoragePath`, the same code works against any backend:
```python
from airflow.io.path import ObjectStoragePath

path = ObjectStoragePath("s3://my-bucket/data/file.csv", conn_id="aws_default")
content = path.read_bytes()

# Switch to GCS — only the URI changes
path = ObjectStoragePath("gs://my-bucket/data/file.csv", conn_id="gcs_default")
content = path.read_bytes()
```

---

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Asset-Driven Scheduling](../31_Asset_Driven_Scheduling/Theory.md)**
