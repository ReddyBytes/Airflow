# HttpOperator — Interview Q&A

> Study guide for Apache Airflow 3. Story-first, beginner-friendly.

---

## Beginner

**Q1. What is the HttpOperator and what problem does it solve?**

Imagine you need your DAG to call a REST API — fetch weather data, trigger a webhook, or notify a Slack channel. Writing raw Python `requests` calls inside a PythonOperator works, but it scatters connection details (host, auth tokens) all over your code. The `HttpOperator` (previously called `SimpleHttpOperator` in Airflow 2) wraps HTTP calls into a dedicated operator, keeping connection credentials in Airflow Connections and making your DAG declarative and auditable.

**Q2. What is `http_conn_id` and why does it matter?**

`http_conn_id` is the ID of an Airflow Connection that stores the base URL (host), port, login, and password for the HTTP service you want to call. Instead of hardcoding `https://api.example.com` in your DAG, you store it once in Airflow's encrypted connection store and reference it by name. This means rotating a token or changing a host URL requires zero DAG code changes.

Default value: `"http_default"`.

**Q3. What is the `endpoint` parameter?**

`endpoint` is the path appended to the base URL from the connection. If your connection host is `https://api.example.com` and `endpoint="/v1/users"`, the operator calls `https://api.example.com/v1/users`. Think of the connection as the domain and `endpoint` as the path.

**Q4. What HTTP methods does HttpOperator support?**

The `method` parameter accepts standard HTTP verbs: `"GET"` (default), `"POST"`, `"PUT"`, `"PATCH"`, `"DELETE"`, `"HEAD"`. Most API interactions — fetching data, submitting forms, updating records — map to one of these.

**Q5. What does HttpOperator return by default?**

By default, HttpOperator returns the raw response body as a string (pushed to XCom as the return value). You can customise the return value using the `response_filter` parameter (a callable that receives the `Response` object).

---

## Intermediate

**Q6. How do you pass custom headers to an HTTP request?**

Use the `headers` parameter, which accepts a plain Python dictionary:

```python
HttpOperator(
    task_id="call_api",
    http_conn_id="my_api",
    endpoint="/data",
    headers={"Content-Type": "application/json", "X-API-Version": "2"},
)
```

For auth tokens, you can put them here: `"Authorization": "Bearer {{ var.value.my_token }}"`.

**Q7. How do you POST JSON data using HttpOperator?**

Set `method="POST"`, pass your payload via `data`, and set the `Content-Type` header:

```python
import json
from airflow.providers.http.operators.http import HttpOperator

post_task = HttpOperator(
    task_id="create_record",
    http_conn_id="my_api",
    endpoint="/records",
    method="POST",
    data=json.dumps({"name": "airflow", "active": True}),
    headers={"Content-Type": "application/json"},
)
```

`data` accepts a string (for JSON) or a dict (which gets form-encoded by the underlying `requests` library).

**Q8. What is `response_check` and when should you use it?**

`response_check` is a callable that receives the `Response` object and must return `True` if the response is considered successful, or `False` (or raise an exception) to mark the task as failed. It lets you add business-logic validation on top of the HTTP status code:

```python
def check_response(response):
    data = response.json()
    return data.get("status") == "ok"

HttpOperator(
    task_id="verify_api",
    http_conn_id="my_api",
    endpoint="/health",
    response_check=check_response,
)
```

Without `response_check`, the operator only fails on non-2xx responses (configurable via `extra_options`).

**Q9. What is `response_filter` and how does it differ from `response_check`?**

`response_check` is a pass/fail gate. `response_filter` is a transformer — it extracts and returns the value you actually want pushed to XCom:

```python
HttpOperator(
    task_id="get_user_id",
    http_conn_id="my_api",
    endpoint="/user/42",
    response_filter=lambda response: response.json()["id"],
)
```

The filtered value (here, just the `id` field) is what downstream tasks receive from XCom. Use `response_filter` when you only care about a subset of the response.

**Q10. How do you pass additional options to the underlying `requests` library?**

Use `extra_options`, a dict that is forwarded directly to `requests.request()`:

```python
HttpOperator(
    task_id="call_api",
    http_conn_id="my_api",
    endpoint="/slow-endpoint",
    extra_options={"timeout": 30, "verify": False},
)
```

Common options: `timeout` (seconds), `verify` (SSL certificate verification), `allow_redirects`, `proxies`.

---

## Advanced

**Q11. How do you handle authentication — Basic Auth, Bearer tokens, and OAuth2?**

Three approaches:

1. **Basic Auth via Connection**: Store username and password in the Airflow Connection. The `HttpHook` (used internally) will inject `Authorization: Basic ...` automatically.

2. **Bearer Token via headers**: Pass the token in the `headers` parameter, optionally pulling it from an Airflow Variable or Secret:
   ```python
   headers={"Authorization": f"Bearer {Variable.get('api_token')}"}
   ```

3. **OAuth2 / dynamic tokens**: Use a PythonOperator before HttpOperator to fetch a fresh token, push it to XCom, then use Jinja templating in `headers`:
   ```python
   headers={"Authorization": "Bearer {{ ti.xcom_pull(task_ids='get_token') }}"}
   ```

**Q12. How do you implement retry logic specifically for HTTP errors (e.g., 429 Too Many Requests)?**

HttpOperator inherits Airflow's `retries` and `retry_delay` parameters for task-level retries. For HTTP-specific retry logic (e.g., only retry on 429 or 503):

1. Use `response_check` to detect the failure condition and raise an exception.
2. Set `retries=3` and `retry_delay=timedelta(seconds=60)` on the operator.
3. For more sophisticated back-off, wrap the call in a PythonOperator using `tenacity` or `requests.adapters.HTTPAdapter` with a `Retry` strategy.

```python
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

def check_not_rate_limited(response):
    if response.status_code == 429:
        raise Exception("Rate limited — will retry")
    return response.status_code < 400
```

**Q13. What is the HttpSensor and when should you use it instead of HttpOperator?**

`HttpSensor` polls an endpoint repeatedly until `response_check` returns `True`. Use it when:
- You're waiting for an async job to complete (e.g., a data export API that returns `{"status": "pending"}`).
- You don't want to block a worker thread — use `mode="reschedule"` to free the worker between polls.

`HttpOperator` is a one-shot call. `HttpSensor` is a polling loop. They are complementary: `HttpOperator` to kick off a job, `HttpSensor` to wait for completion.

**Q14. How do you handle rate limiting across multiple DAG runs making concurrent API calls?**

Several strategies:
1. **Pool**: Assign all HttpOperator tasks that share an API to a named Airflow Pool with a slot count matching your API's concurrency limit.
2. **`max_active_tasks` on the DAG**: Limit how many tasks run simultaneously.
3. **Exponential back-off**: Use `retry_exponential_backoff=True` with `retries` on the operator.
4. **Queue**: Route API-bound tasks to a dedicated worker queue with limited concurrency.

**Q15. What are the differences between HttpOperator in Airflow 2 (SimpleHttpOperator) and Airflow 3?**

In Airflow 2, the operator was named `SimpleHttpOperator`. In Airflow 3:
- It is renamed to `HttpOperator` (import from `airflow.providers.http.operators.http`).
- `response_filter` was added as a first-class parameter (previously required subclassing).
- Better async support and deferrable mode integration.
- The provider (`apache-airflow-providers-http`) is installed separately from the core package.

---

## 📂 Navigation

| | |
|---|---|
| **Parent folder** | [06_All_Operators](../) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Prev operator** | [04_S3Operator](../04_S3Operator/) |
| **Next operator** | [06_DockerOperator](../06_DockerOperator/) |
| **Section root** | [02_Intermediate](../../) |
