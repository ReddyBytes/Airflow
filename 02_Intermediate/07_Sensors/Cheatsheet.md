# 05 — Sensors: Cheatsheet

## Sensor Parameters Quick Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `poke_interval` | float | `60` | Seconds between poke() calls |
| `timeout` | float | `604800` (7 days) | Max seconds before task fails/skips |
| `mode` | str | `"poke"` | `"poke"` or `"reschedule"` |
| `soft_fail` | bool | `False` | Skip instead of fail on timeout |
| `exponential_backoff` | bool | `False` | Grow poke_interval exponentially |
| `silent_fail` | bool | `False` | Log timeout as debug, not error |

---

## poke vs reschedule Mode Comparison

| Aspect | poke | reschedule |
|---|---|---|
| Worker slot | Held the entire time | Released between pokes |
| Resource usage | High (blocks a worker) | Low (worker is freed) |
| Best for | Conditions met in seconds | Conditions met in minutes/hours |
| Risk | Can starve other tasks of workers | Slight overhead from rescheduling |
| Production use | Short waits only | Recommended default |
| Parallelism impact | Low — many poke sensors fill worker pool | High — workers are freed for other tasks |

**Rule of thumb:** If the expected wait is more than 2–3 minutes, use `mode="reschedule"`.

---

## Common Sensors Quick Reference

| Sensor | Import | Key Parameters |
|---|---|---|
| `FileSensor` | `airflow.sensors.filesystem` | `filepath`, `fs_conn_id` |
| `S3KeySensor` | `airflow.providers.amazon.aws.sensors.s3` | `bucket_key`, `bucket_name`, `aws_conn_id` |
| `HttpSensor` | `airflow.providers.http.sensors.http` | `http_conn_id`, `endpoint`, `response_check` |
| `SqlSensor` | `airflow.providers.common.sql.sensors.sql` | `conn_id`, `sql`, `success` |
| `ExternalTaskSensor` | `airflow.sensors.external_task` | `external_dag_id`, `external_task_id`, `execution_delta` |
| `TimeSensor` | `airflow.sensors.time` | `target_time` |
| `PythonSensor` | `airflow.sensors.python` | `python_callable` |
| `BashSensor` | `airflow.sensors.bash` | `bash_command` |

---

## Timeout Best Practices

| Scenario | Recommended timeout | Notes |
|---|---|---|
| Local file from a script | 30–60 minutes | Script should have already run |
| Vendor file via SFTP/S3 | 4–8 hours | Vendors can be late |
| External API health check | 5–15 minutes | If it's been down 15 min, escalate |
| ExternalTaskSensor | Match upstream DAG max duration | Add 20% buffer |
| Database availability | 10–30 minutes | Allow time for DB restarts |

**Never leave timeout at the default (7 days)** — a stuck sensor for 7 days will block your pipeline and burn resources.

---

## Sensor Quick Recipes

### Wait for a file:
```python
FileSensor(task_id="wait", filepath="/data/{{ ds }}/file.csv",
           poke_interval=60, timeout=3600, mode="reschedule")
```

### Wait for S3 key:
```python
S3KeySensor(task_id="wait", bucket_name="my-bucket",
            bucket_key="data/{{ ds }}/file.parquet",
            aws_conn_id="aws_default", poke_interval=60,
            timeout=7200, mode="reschedule")
```

### Wait for HTTP endpoint:
```python
HttpSensor(task_id="wait", http_conn_id="my_api",
           endpoint="/health", poke_interval=30,
           timeout=600, mode="reschedule")
```

### Wait for external DAG task:
```python
ExternalTaskSensor(task_id="wait", external_dag_id="upstream_dag",
                   external_task_id="final_task", mode="reschedule",
                   timeout=7200)
```

### Wait for SQL result:
```python
SqlSensor(task_id="wait", conn_id="my_postgres",
          sql="SELECT COUNT(*) FROM orders WHERE date='{{ ds }}'",
          mode="reschedule", poke_interval=120, timeout=3600)
```

---

## Sensor Decision Guide

```
You need to wait for...
│
├── A file on local disk?                    → FileSensor
├── A file in S3?                            → S3KeySensor
├── An HTTP API to respond OK?               → HttpSensor
├── Another DAG's task to finish?            → ExternalTaskSensor
├── A database query to return rows?         → SqlSensor
├── A specific time of day?                  → TimeSensor / DateTimeSensor
└── A custom Python condition?               → PythonSensor
```
