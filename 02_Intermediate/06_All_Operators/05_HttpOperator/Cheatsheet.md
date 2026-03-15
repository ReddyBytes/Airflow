# HttpOperator — Cheatsheet

> Quick reference for Apache Airflow 3. Provider: `apache-airflow-providers-http`

---

## Install

```bash
pip install apache-airflow-providers-http
```

---

## Import

```python
from airflow.providers.http.operators.http import HttpOperator
from airflow.providers.http.sensors.http import HttpSensor
```

---

## Key Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `http_conn_id` | `str` | `"http_default"` | Airflow Connection ID that stores base URL and optional auth |
| `endpoint` | `str` | `""` | URL path appended to the connection host |
| `method` | `str` | `"GET"` | HTTP method: GET, POST, PUT, PATCH, DELETE, HEAD |
| `data` | `str \| dict` | `None` | Request body. String → raw body (JSON); dict → form-encoded |
| `headers` | `dict` | `None` | HTTP headers dict, e.g. `{"Content-Type": "application/json"}` |
| `response_check` | `callable` | `None` | `fn(response) -> bool` — raises/returns False to fail the task |
| `response_filter` | `callable` | `None` | `fn(response) -> Any` — transforms response pushed to XCom |
| `extra_options` | `dict` | `None` | Forwarded to `requests.request()`, e.g. `{"timeout": 30}` |
| `log_response` | `bool` | `False` | Log the full response body for debugging |
| `deferrable` | `bool` | `False` | Run in async/deferrable mode (Airflow 2.2+) |

---

## Code Patterns

### Basic GET Request

```python
from airflow.providers.http.operators.http import HttpOperator

get_users = HttpOperator(
    task_id="get_users",
    http_conn_id="my_api",        # Connection with host https://api.example.com
    endpoint="/v1/users",
    method="GET",
)
```

### POST with JSON Body

```python
import json

create_record = HttpOperator(
    task_id="create_record",
    http_conn_id="my_api",
    endpoint="/v1/records",
    method="POST",
    data=json.dumps({"name": "airflow", "active": True}),
    headers={"Content-Type": "application/json"},
)
```

### Response Check (Validate Business Logic)

```python
def is_healthy(response):
    body = response.json()
    return body.get("status") == "ok"

health_check = HttpOperator(
    task_id="health_check",
    http_conn_id="my_api",
    endpoint="/health",
    response_check=is_healthy,
)
```

### Response Filter (Extract Value for XCom)

```python
get_token = HttpOperator(
    task_id="get_token",
    http_conn_id="auth_service",
    endpoint="/token",
    method="POST",
    data=json.dumps({"grant_type": "client_credentials"}),
    headers={"Content-Type": "application/json"},
    response_filter=lambda r: r.json()["access_token"],
)
# Downstream: ti.xcom_pull(task_ids="get_token") returns just the token string
```

### Bearer Token Auth

```python
from airflow.models import Variable

HttpOperator(
    task_id="call_protected_api",
    http_conn_id="my_api",
    endpoint="/protected/data",
    headers={"Authorization": f"Bearer {Variable.get('api_token')}"},
)
```

### Timeout and SSL Options

```python
HttpOperator(
    task_id="call_api",
    http_conn_id="my_api",
    endpoint="/data",
    extra_options={"timeout": 30, "verify": True},
)
```

### HTTP Sensor (Poll Until Ready)

```python
from airflow.providers.http.sensors.http import HttpSensor

wait_for_export = HttpSensor(
    task_id="wait_for_export",
    http_conn_id="my_api",
    endpoint="/export/status/{{ run_id }}",
    response_check=lambda r: r.json()["status"] == "done",
    mode="reschedule",          # Free the worker between polls
    poke_interval=60,           # Poll every 60 seconds
    timeout=3600,               # Give up after 1 hour
)
```

---

## Airflow Connection Setup

In the Airflow UI: **Admin → Connections → Add**

| Field | Value |
|-------|-------|
| Conn Id | `my_api` |
| Conn Type | `HTTP` |
| Host | `https://api.example.com` |
| Login | (username for Basic Auth) |
| Password | (password / token for Basic Auth) |
| Extra | `{"Authorization": "Bearer <token>"}` (alternative) |

---

## When to Use HttpOperator

| Situation | Recommendation |
|-----------|----------------|
| Call a REST API once per task | HttpOperator |
| Wait for an async job to finish | HttpSensor with `mode="reschedule"` |
| Complex auth flows (OAuth2, multi-step) | PythonOperator + `requests` library |
| High-volume API calls with custom retry logic | PythonOperator + `tenacity` |
| You need full control over the `requests.Session` | PythonOperator |

---

## When to Avoid HttpOperator

- When you need session-based request pools or connection pooling across tasks.
- When the response is binary (file downloads) — easier to handle in PythonOperator.
- When the API requires multi-step OAuth flows not supported natively.
- When you're making dozens of API calls in a loop — use a single PythonOperator instead of dozens of HttpOperator tasks.

---

## Golden Rules

1. **Always use `http_conn_id`** — never hardcode URLs in DAG files.
2. **Use `response_check` for business logic validation**, not just HTTP status codes.
3. **Use `response_filter` to avoid pushing full response bodies to XCom** — XCom is not designed for large payloads.
4. **Set `extra_options={"timeout": N}`** — never leave HTTP calls without a timeout in production.
5. **Use `HttpSensor` + `mode="reschedule"` for polling** — avoids blocking a worker slot.
6. **Put tokens in Airflow Variables or Secrets Backend**, not hardcoded in `headers`.
7. **Use Pools** to respect API rate limits across concurrent DAG runs.

---

## 📂 Navigation

| | |
|---|---|
| **Parent folder** | [06_All_Operators](../) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Prev operator** | [04_S3Operator](../04_S3Operator/) |
| **Next operator** | [06_DockerOperator](../06_DockerOperator/) |
| **Section root** | [02_Intermediate](../../) |
