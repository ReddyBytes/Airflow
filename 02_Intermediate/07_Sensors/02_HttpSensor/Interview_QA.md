# HttpSensor — Interview Q&A

---

## Beginner Questions

### Q1: What is HttpSensor and what problem does it solve?

**Answer:**

`HttpSensor` is an Airflow sensor that repeatedly polls an HTTP endpoint until it receives a response that satisfies a success condition. It solves the problem of pipelines that need to interact with external APIs or services that aren't always immediately ready.

**Real-world example:** Your pipeline fetches data from a vendor API that runs a nightly processing job. The job finishes somewhere between 5am and 8am. Without `HttpSensor`, you'd either schedule late (wasteful) or handle "data not ready" errors with complex retry logic. With `HttpSensor`, your pipeline simply waits at the door until the API reports it's ready.

```python
from airflow.providers.http.sensors.http import HttpSensor

wait_for_api = HttpSensor(
    task_id="wait_for_api_ready",
    http_conn_id="my_vendor_api",
    endpoint="/v1/status",
    poke_interval=120,
    timeout=4 * 60 * 60,
    mode="reschedule",
)
```

By default, `HttpSensor` considers any HTTP `2xx` response a success. You can add a `response_check` function for more specific validation.

---

### Q2: What is `http_conn_id` and how do you set it up?

**Answer:**

`http_conn_id` is the Airflow Connection ID that holds the base URL (host), port, and optional authentication for the HTTP target. The sensor uses this connection to build the full request URL.

**Setup in Airflow UI (Admin → Connections):**

| Field | Example Value |
|---|---|
| Connection Id | `my_vendor_api` |
| Connection Type | `HTTP` |
| Host | `https://api.vendor.com` |
| Port | (leave blank if in host URL) |
| Login | (username for basic auth, if needed) |
| Password | (password for basic auth, if needed) |

**In the DAG:**
```python
HttpSensor(
    http_conn_id="my_vendor_api",  # References the connection above
    endpoint="/v1/status",          # Appended to the host URL
    # Full URL: https://api.vendor.com/v1/status
)
```

---

### Q3: What does the `endpoint` parameter do?

**Answer:**

`endpoint` is the path appended to the connection's host URL. It represents the relative path of the API endpoint you want to poll.

```python
# Connection host: https://api.example.com
# endpoint: /v2/data/status
# Final URL: https://api.example.com/v2/data/status

HttpSensor(
    http_conn_id="my_api",
    endpoint="/v2/data/status",
    request_params={"date": "{{ ds }}"},
    # Final URL: https://api.example.com/v2/data/status?date=2024-01-15
)
```

`endpoint` supports Jinja templating, so you can build date-based paths:
```python
endpoint="/v1/reports/{{ ds }}/status"
# → /v1/reports/2024-01-15/status
```

---

### Q4: What is the `response_check` function?

**Answer:**

`response_check` is an optional Python callable that receives the HTTP `requests.Response` object and returns `True` (condition met — sensor succeeds) or `False` (not ready yet — keep waiting).

Without `response_check`, any `2xx` HTTP status code counts as success. With `response_check`, you add custom business logic on top:

```python
def check_data_is_ready(response) -> bool:
    """API must return 200 with status='ready' and non-zero record count."""
    if response.status_code != 200:
        return False
    try:
        data = response.json()
        return (
            data.get("status") == "ready" and
            data.get("record_count", 0) > 0
        )
    except ValueError:
        return False  # Not valid JSON — keep waiting

HttpSensor(
    task_id="wait_for_data",
    http_conn_id="my_api",
    endpoint="/status",
    response_check=check_data_is_ready,  # Custom logic
    poke_interval=60,
    timeout=3600,
    mode="reschedule",
)
```

**Best practice:** Define `response_check` functions outside the DAG at module level so they can be unit-tested independently.

---

### Q5: What HTTP methods does HttpSensor support?

**Answer:**

`HttpSensor` supports any HTTP method via the `method` parameter (default: `GET`).

```python
# GET (default) — most common for health checks
HttpSensor(method="GET", endpoint="/health", ...)

# POST — when the endpoint requires a POST to trigger a check
HttpSensor(
    method="POST",
    endpoint="/api/check-status",
    headers={"Content-Type": "application/json"},
    request_params={"date": "{{ ds }}"},
    ...
)
```

For most polling/health-check use cases, `GET` is the right choice. Use `POST` only when the API's status endpoint explicitly requires it.

---

## Intermediate Questions

### Q6: How do you add authentication headers to HttpSensor?

**Answer:**

There are two approaches, depending on the auth type:

**Option 1 — Headers parameter (Bearer token, API key):**
```python
HttpSensor(
    task_id="wait_for_api",
    http_conn_id="my_api",
    endpoint="/status",
    headers={
        "Authorization": "Bearer {{ var.value.api_token }}",
        "X-API-Key": "{{ var.value.api_key }}",
        "Accept": "application/json",
    },
    response_check=lambda r: r.status_code == 200,
)
```

**Option 2 — Connection credentials (Basic Auth):**
Set the `Login` and `Password` in the Airflow Connection. The HTTP provider automatically adds the `Authorization: Basic ...` header using these credentials.

**Best practice:** Store tokens in Airflow Variables or Secrets Backend, not hardcoded in the DAG. Reference them via `{{ var.value.my_token }}` in Jinja-templated fields.

---

### Q7: What is the difference between HttpSensor and SimpleHttpOperator?

**Answer:**

Both use the same HTTP provider and connection, but serve completely different purposes:

| Aspect | `HttpSensor` | `SimpleHttpOperator` |
|---|---|---|
| Purpose | **Wait** until an endpoint is ready | **Perform** an HTTP action and capture result |
| Behavior | Pokes repeatedly until `response_check` returns `True` | Executes once, stores result in XCom |
| Return value | Nothing — signals success/failure | HTTP response text pushed to XCom |
| Use case | Gate/wait pattern | Fetch data, trigger webhooks |

**Typical pattern:** Use `HttpSensor` to confirm the API is ready, then use `SimpleHttpOperator` to actually fetch the data:

```python
wait_for_api = HttpSensor(
    task_id="wait_for_api",
    http_conn_id="my_api",
    endpoint="/status",
    response_check=lambda r: r.json().get("status") == "ready",
    mode="reschedule",
)

fetch_data = SimpleHttpOperator(
    task_id="fetch_data",
    http_conn_id="my_api",
    endpoint="/v1/data",
    method="GET",
    response_filter=lambda r: r.text,
)

wait_for_api >> fetch_data
```

---

### Q8: How do you handle SSL verification in HttpSensor?

**Answer:**

`HttpSensor` passes SSL options through the `extra_options` parameter, which is forwarded to the underlying `requests` library:

```python
# Disable SSL verification (dev/test only — NEVER in production)
HttpSensor(
    task_id="wait_for_internal_api",
    http_conn_id="internal_api",
    endpoint="/health",
    extra_options={"verify": False},
    poke_interval=30,
    timeout=600,
)

# Use a custom CA certificate bundle
HttpSensor(
    extra_options={"verify": "/path/to/ca_bundle.crt"},
    ...
)
```

**Warning:** `verify=False` disables certificate validation and is a security risk. Only use it in isolated dev/test environments. In production, provide a proper CA bundle or fix the certificate chain.

---

### Q9: How do you add query parameters to the HTTP request?

**Answer:**

Use the `request_params` parameter. It accepts a dictionary that is appended as query string parameters:

```python
HttpSensor(
    task_id="wait_for_daily_data",
    http_conn_id="my_api",
    endpoint="/v1/availability",
    request_params={
        "date": "{{ ds }}",        # 2024-01-15
        "source": "orders",
        "format": "json",
    },
    # Final URL: /v1/availability?date=2024-01-15&source=orders&format=json
    response_check=lambda r: r.json().get("available") is True,
    mode="reschedule",
    poke_interval=120,
    timeout=3600,
)
```

`request_params` values support Jinja templating — `{{ ds }}`, `{{ ds_nodash }}`, `{{ var.value.my_var }}`, etc. are all rendered before the request is made.

---

## Advanced Questions

### Q10: How does HttpSensor behave when the endpoint returns a non-2xx status?

**Answer:**

By default, non-2xx responses (4xx, 5xx) cause `HttpSensor` to **raise an exception**, which marks the task as failed — not as "keep waiting." This is often surprising.

To make the sensor treat error responses as "not ready yet" (keep poking), wrap the check in the `response_check` function:

```python
def check_with_error_handling(response) -> bool:
    # Treat 503 (Service Unavailable) as "not ready yet"
    if response.status_code == 503:
        print("Service temporarily unavailable — will retry")
        return False
    # Treat 500 as a fatal error — re-raise to fail the task
    if response.status_code == 500:
        raise Exception(f"API returned 500: {response.text}")
    # Treat 200 with ready status as success
    if response.status_code == 200:
        return response.json().get("status") == "ready"
    return False

HttpSensor(
    task_id="wait_with_error_handling",
    http_conn_id="my_api",
    endpoint="/status",
    response_check=check_with_error_handling,
    mode="reschedule",
    poke_interval=60,
    timeout=3600,
)
```

The key insight: **returning `False` from `response_check` = keep waiting; raising an exception = fail the task immediately**.

---

### Q11: How do you test a `response_check` function without running a DAG?

**Answer:**

Since `response_check` functions are pure Python callables that accept a `requests.Response` object, they can be unit-tested directly using `unittest.mock`:

```python
from unittest.mock import MagicMock

def check_data_ready(response) -> bool:
    data = response.json()
    return data.get("status") == "ready" and data.get("count", 0) > 0

# Test it without Airflow or any HTTP calls
def test_check_data_ready():
    # Test "not ready" case
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "processing", "count": 0}
    assert check_data_ready(mock_response) is False

    # Test "ready" case
    mock_response.json.return_value = {"status": "ready", "count": 150}
    assert check_data_ready(mock_response) is True

    # Test missing fields
    mock_response.json.return_value = {}
    assert check_data_ready(mock_response) is False
```

This is a major advantage of defining `response_check` outside the DAG — it becomes a plain testable function with no Airflow dependencies.

---

### Q12: HttpSensor vs writing a PythonSensor for HTTP checks — when would you choose each?

**Answer:**

Both can poll an HTTP endpoint, but they have different trade-offs:

| Aspect | `HttpSensor` | `PythonSensor` with `requests` |
|---|---|---|
| Setup | Requires Airflow Connection | No connection needed |
| Auth storage | Managed by Airflow Connections | Must manage credentials yourself |
| Code complexity | Low (response_check function) | Higher (full requests call) |
| Flexibility | Limited to HTTP options exposed | Full `requests` library control |
| SSL/proxy control | Via `extra_options` | Direct `requests` session control |
| Retries on error | May fail on non-2xx | Full control over error handling |

**Choose `HttpSensor` when:**
- The connection/credential is already managed in Airflow Connections
- The check is a straightforward status-endpoint poll
- You want the standard sensor monitoring and logging

**Choose `PythonSensor` when:**
- You need complex session handling (cookies, OAuth flows)
- The endpoint requires a multi-step authentication sequence
- You need to call multiple URLs as part of one "check"
- You want maximum control over retry/error behavior

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [FileSensor](../01_FileSensor/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [ExternalTaskSensor](../03_ExternalTaskSensor/Theory.md)
