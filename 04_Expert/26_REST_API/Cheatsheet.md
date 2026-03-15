# 26 — REST API: Cheatsheet

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## All REST API Endpoints

### System

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Health check for scheduler and metadata DB |
| GET | `/api/v1/version` | Airflow version info |
| GET | `/api/v1/config` | Airflow config (non-sensitive sections) |

### DAGs

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/dags` | List all DAGs |
| GET | `/api/v1/dags/{dag_id}` | Get DAG details |
| PATCH | `/api/v1/dags/{dag_id}` | Update DAG (pause/unpause) |
| DELETE | `/api/v1/dags/{dag_id}` | Delete DAG metadata |
| GET | `/api/v1/dags/{dag_id}/tasks` | List tasks in a DAG |
| GET | `/api/v1/dags/{dag_id}/tasks/{task_id}` | Get task details |
| GET | `/api/v1/dags/{dag_id}/source` | Get DAG source code |

### DAG Runs

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/dags/{dag_id}/dagRuns` | Trigger a DAG run |
| GET | `/api/v1/dags/{dag_id}/dagRuns` | List DAG runs |
| GET | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}` | Get a specific run |
| PATCH | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}` | Update run state |
| DELETE | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}` | Delete a run |
| POST | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/clear` | Clear run tasks |
| POST | `/api/v1/dagRuns/list` | Batch list runs across DAGs |

### Task Instances

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances` | List task instances |
| GET | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}` | Get specific TI |
| PATCH | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}` | Set TI state |
| POST | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/clear` | Clear task instances |
| GET | `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}` | Get task logs |

### Variables

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/variables` | List variables |
| POST | `/api/v1/variables` | Create variable |
| GET | `/api/v1/variables/{variable_key}` | Get variable |
| PATCH | `/api/v1/variables/{variable_key}` | Update variable |
| DELETE | `/api/v1/variables/{variable_key}` | Delete variable |

### Connections

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/connections` | List connections |
| POST | `/api/v1/connections` | Create connection |
| GET | `/api/v1/connections/{connection_id}` | Get connection |
| PATCH | `/api/v1/connections/{connection_id}` | Update connection |
| DELETE | `/api/v1/connections/{connection_id}` | Delete connection |
| POST | `/api/v1/connections/test` | Test a connection |

### Pools

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/pools` | List pools |
| POST | `/api/v1/pools` | Create pool |
| GET | `/api/v1/pools/{pool_name}` | Get pool |
| PATCH | `/api/v1/pools/{pool_name}` | Update pool |
| DELETE | `/api/v1/pools/{pool_name}` | Delete pool |

---

## Auth Header Format

```bash
# JWT Bearer (production)
-H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Basic auth (development only)
-u admin:admin
# or equivalently:
-H "Authorization: Basic $(echo -n 'admin:admin' | base64)"
```

### Get JWT Token
```bash
TOKEN=$(curl -s -X POST "http://localhost:8080/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}' | jq -r '.access_token')
```

---

## Common curl One-Liners

```bash
# Trigger DAG immediately (no logical_date)
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{}' "http://localhost:8080/api/v1/dags/MY_DAG/dagRuns"

# Trigger with conf
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"conf": {"key": "value"}}' "http://localhost:8080/api/v1/dags/MY_DAG/dagRuns"

# Get latest run state
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/MY_DAG/dagRuns?limit=1&order_by=-execution_date" \
  | jq -r '.dag_runs[0].state'

# Unpause a DAG
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"is_paused": false}' "http://localhost:8080/api/v1/dags/MY_DAG"

# List failed runs in last 24h
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/dags/MY_DAG/dagRuns?state=failed&limit=10" | jq '.dag_runs[].dag_run_id'

# Create a variable
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"key": "my_key", "value": "my_value"}' "http://localhost:8080/api/v1/variables"

# Health check (no auth required)
curl http://localhost:8080/api/v1/health | jq
```

---

## Pagination Parameters

| Parameter | Type | Description | Default |
|---|---|---|---|
| `limit` | int | Max items per response | 100 |
| `offset` | int | Items to skip | 0 |
| `order_by` | string | Sort field. Prefix with `-` for descending | varies |

### Sorting Examples
- `order_by=execution_date` — oldest first
- `order_by=-execution_date` — newest first
- `order_by=state` — alphabetical by state
- `order_by=dag_id` — alphabetical by DAG ID

### Pagination Response Shape
```json
{
    "dag_runs": [...],
    "total_entries": 1547
}
```

---

## Response Status Codes

| Code | Meaning | Common Cause |
|---|---|---|
| 200 | OK | Successful GET, PATCH |
| 201 | Created | Successful POST (resource created) |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid request body, missing required field |
| 401 | Unauthorized | Missing or invalid auth token |
| 403 | Forbidden | Authenticated but insufficient permissions |
| 404 | Not Found | DAG ID, run ID, variable key not found |
| 409 | Conflict | DAG run with same ID already exists |
| 422 | Unprocessable Entity | Validation error (e.g., invalid state transition) |
| 500 | Internal Server Error | Airflow bug or DB error |

---

## DAG Run States

| State | Description |
|---|---|
| `queued` | Accepted, waiting for executor |
| `running` | At least one task is running |
| `success` | All tasks succeeded |
| `failed` | At least one task failed |
| `upstream_failed` | Parent task in a TaskGroup failed |

---

## Trigger DAG Run Body

```json
{
    "dag_run_id": "optional_custom_run_id",
    "logical_date": "2026-03-15T00:00:00Z",
    "conf": {
        "any_key": "any_value",
        "date_override": "2026-03-14",
        "debug": false
    },
    "note": "Triggered by CI/CD pipeline v1.2.3"
}
```

All fields are optional. If `dag_run_id` is omitted, Airflow generates `manual__<timestamp>`.
