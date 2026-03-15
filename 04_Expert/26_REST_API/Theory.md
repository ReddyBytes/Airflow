# 26 — REST API

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## The Story

Your CI/CD pipeline deploys a new version of your data models at 3 PM. Immediately after, it needs to trigger the `rebuild_warehouse` DAG to apply those models. Your monitoring tool checks every hour whether the previous night's `nightly_load` succeeded. Your data quality framework needs to know which tasks ran today. None of this happens by having a human click buttons in the Airflow UI — it happens through the REST API.

---

## 1. The API Server in Airflow 3

Airflow 3 separates the web UI and the REST API into distinct components. The **API Server** handles all programmatic access. Key differences from Airflow 2:

| Feature | Airflow 2 | Airflow 3 |
|---|---|---|
| Component | Web Server (Flask) | Separate API Server |
| Default port | 8080 (shared with UI) | 8080 (same port, separate process) |
| API base path | `/api/v1/` | `/api/v1/` (same) |
| Authentication | Basic, Kerberos, custom | JWT Bearer tokens (primary) |
| Authorization | FAB roles | Auth Manager (pluggable) |
| Standalone deployment | No | Yes — can scale independently |

Start the API server:
```bash
airflow api-server --port 8080
```

---

## 2. Authentication

### JWT Token (Recommended)
```bash
# Get token
TOKEN=$(curl -s -X POST "http://localhost:8080/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}' | jq -r '.access_token')

# All subsequent requests
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/dags
```

### Basic Auth (Development Only)
```bash
curl -u admin:admin http://localhost:8080/api/v1/dags
```

---

## 3. Key Endpoints with curl Examples

### Health Check
```bash
# GET /health
curl http://localhost:8080/api/v1/health
# Response: {"metadatabase": {"status": "healthy"}, "scheduler": {"status": "healthy", "latest_scheduler_heartbeat": "2026-03-15T10:00:00Z"}}
```

### DAGs

```bash
# GET /dags — List all DAGs
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags?limit=25&offset=0"

# GET /dags — Filter by tag or only active DAGs
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags?tags=production&only_active=true"

# GET /dags/{dag_id} — Get single DAG
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/my_dag"

# PATCH /dags/{dag_id} — Pause a DAG
curl -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_paused": true}' \
  "http://localhost:8080/api/v1/dags/my_dag"

# PATCH /dags/{dag_id} — Unpause a DAG
curl -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_paused": false}' \
  "http://localhost:8080/api/v1/dags/my_dag"
```

### DAG Runs

```bash
# POST /dags/{dag_id}/dagRuns — Trigger a DAG run
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "dag_run_id": "manual__ci_deploy_v1.2.3",
    "conf": {"env": "production", "version": "v1.2.3"},
    "logical_date": "2026-03-15T10:00:00Z"
  }' \
  "http://localhost:8080/api/v1/dags/rebuild_warehouse/dagRuns"

# Trigger without specifying run_id (Airflow generates one)
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"conf": {"date": "2026-03-15"}}' \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns"

# GET /dags/{dag_id}/dagRuns — List runs
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns?limit=10&order_by=-execution_date"

# GET /dags/{dag_id}/dagRuns — Filter by state
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns?state=failed&limit=5"

# GET /dags/{dag_id}/dagRuns/{dag_run_id} — Get specific run
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns/manual__2026-03-15T10:00:00+00:00"

# DELETE /dags/{dag_id}/dagRuns/{dag_run_id} — Delete a run
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns/manual__2026-03-15T10:00:00+00:00"
```

### Task Instances

```bash
# GET /dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances — List all task instances
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns/manual__2026-03-15/taskInstances"

# GET specific task instance
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns/manual__2026-03-15/taskInstances/my_task"

# POST — Clear (reset) a task instance for retry
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "task_ids": ["my_task"], "include_downstream": false}' \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns/manual__2026-03-15/taskInstances/clear"

# PATCH — Set task instance state (mark as success)
curl -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "new_state": "success"}' \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns/manual__2026-03-15/taskInstances/my_task"
```

### Variables

```bash
# GET /variables — List all variables
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/variables"

# GET /variables/{variable_key} — Get a variable
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/variables/my_variable"

# POST /variables — Create a variable
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "deployment_version", "value": "v1.2.3", "description": "Current deployment"}' \
  "http://localhost:8080/api/v1/variables"

# PATCH /variables/{variable_key} — Update a variable
curl -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "deployment_version", "value": "v1.3.0"}' \
  "http://localhost:8080/api/v1/variables/deployment_version"

# DELETE /variables/{variable_key}
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/variables/old_variable"
```

### Connections

```bash
# GET /connections — List connections (passwords redacted)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/connections"

# POST /connections — Create a connection
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": "postgres_staging",
    "conn_type": "postgres",
    "host": "staging-db.corp.com",
    "login": "airflow_svc",
    "password": "staging_password",
    "port": 5432,
    "schema": "analytics"
  }' \
  "http://localhost:8080/api/v1/connections"

# DELETE /connections/{connection_id}
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/connections/postgres_staging"
```

### Pools

```bash
# GET /pools — List pools
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/pools"

# POST /pools — Create a pool
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "api_calls", "slots": 10, "description": "Rate-limited API calls"}' \
  "http://localhost:8080/api/v1/pools"

# PATCH /pools/{pool_name} — Update pool size
curl -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "api_calls", "slots": 20}' \
  "http://localhost:8080/api/v1/pools/api_calls"
```

---

## 4. Pagination

Most list endpoints support `limit` and `offset` parameters:

```bash
# Page through all DAGs (100 per page)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags?limit=100&offset=0"

# Second page
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags?limit=100&offset=100"
```

Response includes `total_entries` for calculating page count:
```json
{
    "dags": [...],
    "total_entries": 247
}
```

---

## 5. Triggering with conf and Polling for Completion

The most common CI/CD pattern: trigger a DAG, wait for it to finish, fail the pipeline if the DAG failed.

```bash
#!/bin/bash
# ci_trigger_and_wait.sh

BASE_URL="http://localhost:8080/api/v1"
DAG_ID="rebuild_warehouse"
AUTH="Authorization: Bearer $TOKEN"

# 1. Trigger the DAG
RUN_ID="ci_$(date +%Y%m%d_%H%M%S)"
curl -X POST "$BASE_URL/dags/$DAG_ID/dagRuns" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"dag_run_id\": \"$RUN_ID\", \"conf\": {\"version\": \"$APP_VERSION\"}}"

# 2. Poll until done
while true; do
    STATE=$(curl -s "$BASE_URL/dags/$DAG_ID/dagRuns/$RUN_ID" \
      -H "$AUTH" | jq -r '.state')

    echo "Run $RUN_ID state: $STATE"

    case "$STATE" in
        success) echo "DAG succeeded"; exit 0 ;;
        failed|upstream_failed) echo "DAG FAILED"; exit 1 ;;
        running|queued) sleep 30 ;;
        *) echo "Unknown state: $STATE"; exit 1 ;;
    esac
done
```

---

## Key Takeaways

- Airflow 3 has a dedicated API Server component — scalable independently from the UI
- JWT Bearer tokens are the correct auth method for production API clients
- All list endpoints support `limit`/`offset` pagination with `total_entries` in response
- `conf` dict in POST `/dagRuns` is accessible in DAGs via `{{ dag_run.conf.key }}` or `context['dag_run'].conf`
- DAG run states: `queued`, `running`, `success`, `failed`, `upstream_failed`
- The CI/CD trigger-and-poll pattern is the canonical way to integrate Airflow with deployment pipelines
