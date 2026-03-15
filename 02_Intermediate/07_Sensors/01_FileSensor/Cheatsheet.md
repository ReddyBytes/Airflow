# FileSensor — Cheatsheet

## Quick Reference: Key Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `filepath` | `str` | required | Path to file or glob pattern. Supports Jinja templating. |
| `fs_conn_id` | `str` | `"fs_default"` | Airflow Connection ID for the filesystem |
| `poke_interval` | `float` | `60` | Seconds between each filesystem check |
| `timeout` | `float` | `604800` (7 days) | Max seconds to wait before failing or skipping |
| `mode` | `str` | `"poke"` | `"poke"` (hold worker) or `"reschedule"` (free worker) |
| `soft_fail` | `bool` | `False` | `True` = skip on timeout; `False` = fail on timeout |
| `exponential_backoff` | `bool` | `False` | Double the poke interval after each failed poke |
| `silent_fail` | `bool` | `False` | Log timeout as debug instead of error |

---

## Import

```python
from airflow.sensors.filesystem import FileSensor
```

---

## Code Patterns

### Pattern 1: Basic Usage (Minimal)

```python
FileSensor(
    task_id="wait_for_file",
    filepath="/data/incoming/orders.csv",
)
```

### Pattern 2: Production-Ready with reschedule Mode

```python
from airflow.sensors.filesystem import FileSensor

wait_for_file = FileSensor(
    task_id="wait_for_vendor_file",
    filepath="/data/incoming/vendor_orders_{{ ds_nodash }}.csv",
    fs_conn_id="fs_default",
    poke_interval=60,           # Check every minute
    timeout=6 * 60 * 60,        # Give up after 6 hours
    mode="reschedule",          # Free the worker slot between pokes
    soft_fail=False,            # Hard fail if file never arrives
)
```

### Pattern 3: Dynamic Path with Jinja Date Template

```python
# ds_nodash = YYYYMMDD (e.g. 20240115)
FileSensor(
    task_id="wait_for_dated_file",
    filepath="/data/reports/{{ ds_nodash }}/report.csv",
    poke_interval=120,
    timeout=4 * 60 * 60,
    mode="reschedule",
)

# ds = YYYY-MM-DD (e.g. 2024-01-15)
FileSensor(
    task_id="wait_for_dir",
    filepath="/data/batches/{{ ds }}/",   # trailing slash = directory
    poke_interval=60,
    timeout=3600,
    mode="reschedule",
)
```

### Pattern 4: Wildcard (Glob) Pattern

```python
# Wait for ANY .csv file in today's directory
FileSensor(
    task_id="wait_for_any_csv",
    filepath="/data/incoming/{{ ds }}/*.csv",
    poke_interval=120,
    timeout=8 * 60 * 60,
    mode="reschedule",
)

# Wait for a file matching a prefix and any suffix
FileSensor(
    task_id="wait_for_report",
    filepath="/data/reports/weekly_report_{{ ds_nodash }}*.xlsx",
    poke_interval=300,
    timeout=8 * 60 * 60,
    mode="reschedule",
)
```

### Pattern 5: Optional File with soft_fail

```python
# This file is optional — skip (don't fail) if it never arrives
FileSensor(
    task_id="wait_for_optional_returns",
    filepath="/data/returns_{{ ds_nodash }}.csv",
    poke_interval=60,
    timeout=3600,
    mode="reschedule",
    soft_fail=True,
)

# Downstream task must handle the "skipped" case
process = PythonOperator(
    task_id="process",
    python_callable=my_fn,
    trigger_rule="none_failed",  # Run even if sensor was skipped
)
```

### Pattern 6: Multiple Files in Parallel

```python
wait_sales = FileSensor(task_id="wait_sales",
    filepath="/data/sales_{{ ds_nodash }}.csv",
    mode="reschedule", poke_interval=60, timeout=7200)

wait_returns = FileSensor(task_id="wait_returns",
    filepath="/data/returns_{{ ds_nodash }}.csv",
    mode="reschedule", poke_interval=60, timeout=7200,
    soft_fail=True)  # optional

# Both sensors run in parallel; process_all waits for both
[wait_sales, wait_returns] >> process_all
```

### Pattern 7: Exponential Backoff

```python
FileSensor(
    task_id="wait_with_backoff",
    filepath="/data/slow_delivery_{{ ds_nodash }}.csv",
    poke_interval=30,           # Starts at 30s, then 60s, 120s, 240s...
    exponential_backoff=True,
    timeout=4 * 60 * 60,
    mode="reschedule",
)
```

---

## When to Use FileSensor

**Use it when:**
- Waiting for vendor/partner file deliveries to a local or NFS-mounted path
- Gating a pipeline until an upstream script finishes writing a file
- Checking for a "done" sentinel file or `_SUCCESS` flag on the worker filesystem
- Simple, path-based existence check is all you need

**Avoid it when:**
- Files are in AWS S3 → use `S3KeySensor` instead
- Files are on a remote SFTP server → use `SFTPSensor` instead
- You need to check file content or size, not just existence → use a `PythonSensor`
- You need to watch multiple complex patterns → consider a dedicated monitoring solution

---

## poke vs reschedule Decision

```
Expected wait time?
│
├── Under 2 minutes?       → mode="poke" is acceptable
└── Over 2 minutes?        → ALWAYS use mode="reschedule"
    │
    └── Reason: poke mode holds a worker slot the entire time.
        In reschedule mode, the worker is freed between checks.
        For vendor files that may arrive hours later,
        poke mode can exhaust your worker pool.
```

---

## Golden Rules

1. **Always set `timeout`** — the default is 7 days. Set it to a realistic value (e.g., 4–8 hours for vendor files).
2. **Use `mode="reschedule"` in production** — never hold a worker slot for hours.
3. **Use `soft_fail=True` for optional files** — combine with `trigger_rule="none_failed"` downstream.
4. **Test your Jinja templates** — a wrong date format is the #1 cause of unexpected FileSensor timeouts.
5. **Check worker-side filesystem access** — the sensor runs on the worker, not the scheduler. Verify the worker can actually see the path.
6. **Use glob patterns wisely** — `FileSensor` returns `True` on the first match. You still need `glob.glob()` in your downstream task to get the actual filenames.

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| `mode="poke"` for long waits | Change to `mode="reschedule"` |
| Leaving `timeout=604800` (default) | Set a realistic timeout, e.g. `timeout=14400` |
| File exists but sensor times out | Check worker filesystem access and Jinja template rendering |
| Using `soft_fail=True` without `trigger_rule` downstream | Add `trigger_rule="none_failed"` to downstream tasks |
| Waiting for files on S3 with FileSensor | Use `S3KeySensor` instead |

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ **Cheatsheet.md** | ← you are here |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview questions |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [Sensors Overview](../Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [HttpSensor](../02_HttpSensor/Theory.md)
