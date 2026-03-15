# Airflow 3 — What's New: Cheatsheet

## Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Asset-Driven Scheduling](../31_Asset_Driven_Scheduling/Theory.md)**

---

## Command Changes: v2 → v3

| Airflow 2 Command | Airflow 3 Command | Notes |
|-------------------|-------------------|-------|
| `airflow webserver` | `airflow api-server` | Serves UI + REST API |
| `airflow db init` | `airflow db migrate` | Also replaces `db upgrade` |
| `airflow db upgrade` | `airflow db migrate` | Single command for all DB ops |
| `airflow scheduler` | `airflow scheduler` | Unchanged |
| (not available) | `airflow dag-processor` | New required component |
| (not available) | `airflow edge worker` | New edge executor component |

---

## Removed Features

| Feature | Removed In | Replacement |
|---------|-----------|-------------|
| `SubDagOperator` | Airflow 3.0 | `TaskGroup` |
| `airflow db init` | Airflow 3.0 | `airflow db migrate` |
| `airflow webserver` | Airflow 3.0 | `airflow api-server` |
| `provide_context=True` | Airflow 3.0 | Always provided, remove the param |
| `execution_date` in context | Airflow 3.0 | `logical_date` |
| FAB as default auth | Airflow 3.0 | Simple Auth Manager (dev) |
| `Dataset` class (old name) | Airflow 3.0 | `Asset` class |
| `/api/v1/` REST endpoints | Airflow 3.0 | `/api/v2/` |

---

## Import Changes: v2 → v3

```python
# v2
from airflow.datasets import Dataset
from airflow.operators.subdag import SubDagOperator

# v3
from airflow.sdk import Asset
from airflow.utils.task_group import TaskGroup  # unchanged
```

---

## New Features at a Glance

| Feature | What It Does |
|---------|-------------|
| **Assets** | Renamed Datasets + `@asset` decorator + aliases |
| **Edge Executor** | Run tasks on remote/lightweight nodes via HTTP |
| **Auth Manager** | Pluggable auth: swap FAB, LDAP, OAuth, custom |
| **DAG Versioning** | Historical runs show the DAG version active at run time |
| **ObjectStorage API** | Unified file I/O: S3/GCS/Azure/local via one API |
| **React UI** | Completely rewritten SPA — faster, cleaner |
| **DAG Processor** | Isolated DAG parsing process — crashes don't kill Scheduler |
| **Internal API** | All inter-component comms via HTTP API, not direct DB |
| **Event-driven scheduling** | Webhooks + Assets trigger DAG runs |

---

## Architecture: New Required Components

```
Airflow 2 deployment:  scheduler + webserver + worker
Airflow 3 deployment:  scheduler + api-server + dag-processor + worker
```

The `dag-processor` is a new required service. Without it, DAGs are not parsed.

---

## Config File Changes

```ini
# v2 airflow.cfg
[webserver]
rbac = True
base_url = http://localhost:8080

# v3 airflow.cfg
[api_server]
base_url = http://localhost:8080

[core]
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager
# OR for development:
auth_manager = airflow.auth.managers.simple.SimpleAuthManager

[dag_processor]
# DAG processor settings moved here from [scheduler]
```

---

## Breaking Changes Checklist

- [ ] `Dataset` → `Asset` (rename import and class usage)
- [ ] `SubDagOperator` → `TaskGroup` (refactor all SubDAGs)
- [ ] Remove `provide_context=True` from all `PythonOperator` calls
- [ ] `context["execution_date"]` → `context["logical_date"]`
- [ ] `airflow db init` → `airflow db migrate` in all scripts
- [ ] `airflow webserver` → `airflow api-server` in all startup scripts
- [ ] Add `dag-processor` to Docker Compose / Kubernetes deployment
- [ ] Update REST API clients: `/api/v1/` → `/api/v2/`
- [ ] Set `auth_manager` in config if using non-default auth

---

## Docker Compose Quick Reference

```yaml
# Airflow 3 — new services needed
services:
  api-server:           # was: webserver
    command: api-server
    ports: ["8080:8080"]

  dag-processor:        # NEW in v3
    command: dag-processor

  scheduler:            # unchanged
    command: scheduler

  worker:               # unchanged (if using Celery)
    command: celery worker
```

---

## Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Asset-Driven Scheduling](../31_Asset_Driven_Scheduling/Theory.md)**
