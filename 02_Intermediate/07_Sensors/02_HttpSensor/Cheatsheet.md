# HttpSensor — Cheatsheet

## Quick Reference: Key Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `http_conn_id` | `str` | `"http_default"` | Airflow Connection ID for the HTTP target |
| `endpoint` | `str` | `""` | Relative path appended to the connection host URL |
| `method` | `str` | `"GET"` | HTTP method: `"GET"`, `"POST"`, `"PUT"`, etc. |
| `request_params` | `dict` | `None` | Query string parameters (Jinja-supported values) |
| `headers` | `dict` | `None` | HTTP headers to include in every request |
| `response_check` | `Callable` | `None` | Function: `(Response) -> bool`. Custom success condition. |
| `extra_options` | `dict` | `None` | Extra kwargs passed to `requests` (e.g. `{"verify": False}`) |
| `poke_interval` | `float` | `60` | Seconds between HTTP requests |
| `timeout` | `float` | `604800` | Max seconds before task fails or skips |
| `mode` | `str` | `"poke"` | `"poke"` or `"reschedule"` |
| `soft_fail` | `bool` | `False` | Skip instead of fail on timeout |

---

## Import

```python
from airflow.providers.http.sensors.http import HttpSensor
```

**Provider install:**
```bash
pip install apache-airflow-providers-http
```

---

## Code Patterns

### Pattern 1: Basic Health Check (any 2xx = success)

```python
HttpSensor(
    task_id="check_service_is_up",
    http_conn_id="my_api",
    endpoint="/health",
    poke_interval=30,
    timeout=10 * 60,     # 10 minutes
    mode="reschedule",
)
```

When no `response_check` is provided, any `2xx` HTTP response counts as success.

---

### Pattern 2: Check for JSON Key in Response

```python
def check_data_ready(response) -> bool:
    try:
        data = response.json()
        return data.get("status") == "ready" and data.get("record_count", 0) > 0
    except ValueError:
        return False  # Not JSON yet — keep waiting

HttpSensor(
    task_id="wait_for_data_availability",
    http_conn_id="my_data_api",
    endpoint="/v1/status",
    request_params={"date": "{{ ds }}"},
    response_check=check_data_ready,
    poke_interval=120,
    timeout=6 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 3: With Authentication Headers

```python
HttpSensor(
    task_id="wait_for_secure_api",
    http_conn_id="my_api",
    endpoint="/api/status",
    headers={
        "Authorization": "Bearer {{ var.value.api_token }}",
        "Accept": "application/json",
        "X-Request-Source": "airflow",
    },
    response_check=lambda r: r.json().get("available") is True,
    poke_interval=60,
    timeout=3600,
    mode="reschedule",
)
```

---

### Pattern 4: POST Request with Body Check

```python
def check_job_complete(response) -> bool:
    if response.status_code == 202:
        progress = response.json().get("progress_percent", 0)
        print(f"Job {progress}% complete — still waiting")
        return False
    return response.status_code == 200

HttpSensor(
    task_id="wait_for_async_job",
    http_conn_id="my_api",
    endpoint="/jobs/{{ var.value.current_job_id }}/status",
    method="POST",
    headers={"Content-Type": "application/json"},
    response_check=check_job_complete,
    poke_interval=30,
    timeout=2 * 60 * 60,
    mode="reschedule",
)
```

---

### Pattern 5: Handle Non-2xx Without Failing

By default, 4xx/5xx responses raise an exception and fail the task. To treat them as "not ready yet," handle them inside `response_check`:

```python
def tolerant_check(response) -> bool:
    if response.status_code in (503, 429):
        # Service unavailable or rate-limited — keep waiting
        print(f"Got {response.status_code} — retrying later")
        return False
    if response.status_code == 200:
        return response.json().get("status") == "ready"
    # Any other unexpected code raises to fail the task
    response.raise_for_status()
    return False

HttpSensor(
    task_id="wait_tolerant",
    http_conn_id="my_api",
    endpoint="/status",
    response_check=tolerant_check,
    mode="reschedule",
    poke_interval=60,
    timeout=3600,
)
```

---

### Pattern 6: Disable SSL Verification (dev/test only)

```python
HttpSensor(
    task_id="check_internal_service",
    http_conn_id="internal_dev_api",
    endpoint="/health",
    extra_options={"verify": False},  # NEVER use in production
    poke_interval=15,
    timeout=300,
)
```

---

## When to Use / Avoid

**Use HttpSensor when:**
- Upstream API has maintenance windows or delayed data availability
- You need to confirm data is ready before fetching it with `SimpleHttpOperator`
- Polling a job-status endpoint for async processing completion
- Gating the pipeline until an external service reports healthy

**Avoid HttpSensor when:**
- The API should always be up (monitor it with alerting tools instead)
- The check requires multi-step OAuth flows (use `PythonSensor` instead)
- You need to capture the response content for downstream use (use `SimpleHttpOperator` directly)
- Simple immediate API calls with no waiting needed

---

## response_check Function Rules

```
response_check(response: requests.Response) -> bool
│
├── Return True  → condition met → sensor task SUCCEEDS
├── Return False → condition not met → wait poke_interval then poke again
└── Raise exception → sensor task FAILS immediately
```

**Available on the `response` object:**
- `response.status_code` — HTTP status (200, 404, 503, etc.)
- `response.json()` — parse body as JSON (raises `ValueError` if not JSON)
- `response.text` — body as string
- `response.headers` — response headers dict
- `response.raise_for_status()` — raises exception for 4xx/5xx

---

## Golden Rules

1. **Define `response_check` outside the DAG** — makes it unit-testable with `unittest.mock`.
2. **Return `False` for "not ready yet," raise for fatal errors** — this gives you fine-grained control over poke vs fail behavior.
3. **Use `mode="reschedule"` for waits > 2 minutes** — never block a worker slot for hours.
4. **Always set a realistic `timeout`** — if the API is down for 7 days, you don't want a stuck sensor.
5. **Store tokens in Airflow Variables or Secrets Backend** — reference via `{{ var.value.my_token }}` in `headers`.
6. **Include `print()` statements in `response_check`** — they appear in task logs and are invaluable for debugging long waits.

---

## HttpSensor vs SimpleHttpOperator

| | HttpSensor | SimpleHttpOperator |
|---|---|---|
| Purpose | Wait until endpoint is ready | Execute HTTP call, capture response |
| Runs | Repeatedly (pokes) | Once |
| Result | Task success/failure | Response text pushed to XCom |
| Use | Gate before data fetch | Actual data fetch or webhook trigger |

Typical pipeline: `HttpSensor` → `SimpleHttpOperator` → `PythonOperator`

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ **Cheatsheet.md** | ← you are here |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview questions |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [FileSensor](../01_FileSensor/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [ExternalTaskSensor](../03_ExternalTaskSensor/Theory.md)
