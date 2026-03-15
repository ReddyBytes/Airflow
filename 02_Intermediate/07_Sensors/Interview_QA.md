# 05 — Sensors: Interview Q&A

## Q1: What is a sensor in Apache Airflow?

**Answer:**

A sensor is a special type of operator that waits for a condition to become true before allowing the pipeline to continue. Instead of running once and finishing, a sensor repeatedly calls its `poke()` method at a set interval until the condition is met or a timeout is reached.

Examples:
- `FileSensor` waits for a file to appear
- `HttpSensor` waits for an API to return a successful response
- `ExternalTaskSensor` waits for another DAG's task to complete

Sensors inherit from `BaseSensorOperator`, which itself inherits from `BaseOperator`.

---

## Q2: What is the difference between poke mode and reschedule mode?

**Answer:**

Both modes control how the sensor checks the condition, but they differ in resource usage:

**poke mode (default):**
- The sensor holds its worker slot for the entire duration of waiting
- The worker process keeps running, sleeping between pokes
- Good for short waits (seconds to a couple of minutes)
- Problem: many poke sensors can fill up your worker pool, starving real tasks

**reschedule mode:**
- The sensor pokes, finds the condition not met, then releases its worker slot
- It schedules itself to be re-checked after `poke_interval`
- The worker is free to do other work between checks
- Best practice for any wait longer than a few minutes
- Set with: `mode="reschedule"`

In production, always default to `mode="reschedule"` unless the wait is very short.

---

## Q3: What happens when a sensor times out?

**Answer:**

When the sensor's `timeout` (in seconds) is exceeded without the condition being met:

- By default (`soft_fail=False`): the task is marked as **failed** — this can trigger `on_failure_callback`, email alerts, and cascade failures to downstream tasks.

- With `soft_fail=True`: the task is marked as **skipped** — downstream tasks are also skipped unless they have a `trigger_rule` that handles skipped upstreams (like `none_failed` or `all_done`).

```python
# Default: failure on timeout
FileSensor(task_id="wait", filepath="/data/file.csv", timeout=3600)

# Soft fail: skip on timeout (no error cascade)
FileSensor(task_id="wait_optional", filepath="/data/optional.csv",
           timeout=1800, soft_fail=True)
```

---

## Q4: How do you create a custom sensor?

**Answer:**

Subclass `BaseSensorOperator` and implement the `poke()` method. Return `True` to signal the condition is met, `False` to keep waiting.

```python
from airflow.sensors.base import BaseSensorOperator

class MyDatabaseReadySensor(BaseSensorOperator):

    def __init__(self, table_name: str, min_rows: int, conn_id: str, **kwargs):
        super().__init__(**kwargs)
        self.table_name = table_name
        self.min_rows = min_rows
        self.conn_id = conn_id

    def poke(self, context) -> bool:
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        hook = PostgresHook(postgres_conn_id=self.conn_id)
        result = hook.get_first(
            f"SELECT COUNT(*) FROM {self.table_name} WHERE date = '{context['ds']}'"
        )
        count = result[0] if result else 0

        self.log.info(f"Found {count} rows (need {self.min_rows})")
        return count >= self.min_rows
```

---

## Q5: What is the difference between a Sensor and an Operator?

**Answer:**

| | Operator | Sensor |
|---|---|---|
| Purpose | Perform an action | Wait for a condition |
| Base class | `BaseOperator` | `BaseSensorOperator` (which extends `BaseOperator`) |
| Key method | `execute()` — called once | `poke()` — called repeatedly |
| Blocking | Finishes in one call | Can wait minutes/hours |
| Return value | Result of the action | `True` (done) or `False` (not yet) |

In short: operators **do** things, sensors **wait** for things.

---

## Q6: What is poke_interval and how should you set it?

**Answer:**

`poke_interval` (in seconds) controls how often the sensor checks the condition. The default is 60 seconds.

Setting it correctly depends on the use case:
- **Too low**: wastes resources, puts unnecessary load on the monitored system (e.g., hammering an API every second)
- **Too high**: you might wait longer than necessary after the condition is met

| Scenario | Recommended poke_interval |
|---|---|
| Waiting for a file on local disk | 30–60 seconds |
| Waiting for S3 key | 60–120 seconds |
| HTTP health check | 15–30 seconds |
| ExternalTaskSensor | 30–60 seconds |
| SQL row count check | 120–300 seconds |

---

## Q7: What is ExternalTaskSensor used for?

**Answer:**

`ExternalTaskSensor` waits for a task in a **different DAG** to complete. It is the standard way to create dependencies between separate DAGs.

```python
ExternalTaskSensor(
    task_id="wait_for_upstream",
    external_dag_id="upstream_data_pipeline",
    external_task_id="load_complete",
    mode="reschedule",
    poke_interval=60,
    timeout=7200,
)
```

Common pitfall: `ExternalTaskSensor` matches on execution dates. If the two DAGs run on different schedules, the dates won't match. Use `execution_delta` to offset:

```python
ExternalTaskSensor(
    external_dag_id="hourly_dag",
    execution_delta=timedelta(hours=1),  # Look for run 1 hour behind current run
)
```

---

## Q8: What is the difference between FileSensor and S3KeySensor?

**Answer:**

- `FileSensor` checks for a file on the **local filesystem** of the Airflow worker. It uses a filesystem connection (`fs_conn_id`).
- `S3KeySensor` checks for an object key in **AWS S3**. It uses an AWS connection (`aws_conn_id`).

Use `FileSensor` when files are mounted or local. Use `S3KeySensor` when files are stored in S3 (cloud storage). For most modern pipelines, `S3KeySensor` is more common.

---

## Q9: What is HttpSensor and what does the response_check function do?

**Answer:**

`HttpSensor` polls an HTTP endpoint. By default, it considers any `2xx` response a success. You can add a `response_check` function to apply custom logic:

```python
def check_data_is_ready(response) -> bool:
    data = response.json()
    return data.get("status") == "ready" and data.get("record_count", 0) > 0

HttpSensor(
    task_id="wait_for_api",
    http_conn_id="my_api",
    endpoint="/status",
    response_check=check_data_is_ready,  # Custom validation
    poke_interval=30,
    timeout=600,
)
```

`response_check` receives the `requests.Response` object and must return `True` (ready) or `False` (not yet ready).

---

## Q10: How do you prevent sensors from consuming all your worker slots?

**Answer:**

Several strategies:

1. **Use `mode="reschedule"`** — This is the most important change. Reschedule mode releases the worker slot between pokes.

2. **Use a dedicated sensor pool** — Create a pool specifically for sensors with a limited number of slots, separate from your main task pool:
```python
FileSensor(
    task_id="wait",
    filepath="/data/file.csv",
    pool="sensors_pool",  # Limit how many sensors run simultaneously
    mode="reschedule",
)
```

3. **Set reasonable poke_interval** — Don't poke every second; poke every 30–120 seconds for most use cases.

4. **Set timeouts** — Sensors that time out release their slot. Always set a realistic `timeout`.

5. **Use `smart_sensor_operator`** (Airflow 2.x) — consolidates multiple sensors into a single worker process (advanced optimization for high-sensor deployments).
