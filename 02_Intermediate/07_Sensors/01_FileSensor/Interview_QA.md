# FileSensor — Interview Q&A

---

## Beginner Questions

### Q1: What is FileSensor and what problem does it solve?

**Answer:**

`FileSensor` is a built-in Airflow sensor that waits for a file (or directory) to exist at a specified path before allowing the pipeline to continue.

**The problem it solves:** Imagine your DAG runs every morning at 6am to process a vendor file. The vendor drops the file somewhere between 6am and 10am — you never know exactly when. Without a sensor, you'd either schedule your DAG late (wasting time on days the file arrives early) or handle file-not-found errors with awkward retry logic.

`FileSensor` elegantly solves this: it starts immediately, pokes the filesystem every N seconds, and the moment the file appears, the pipeline continues. If the file never arrives, it gives up after the configured `timeout`.

```python
from airflow.sensors.filesystem import FileSensor

wait_for_file = FileSensor(
    task_id="wait_for_vendor_file",
    filepath="/data/incoming/vendor_orders_{{ ds_nodash }}.csv",
    fs_conn_id="fs_default",
    poke_interval=60,
    timeout=4 * 60 * 60,
    mode="reschedule",
)
```

---

### Q2: What does the `filepath` parameter accept?

**Answer:**

`filepath` is the path to the file or directory you're waiting for. It accepts:

1. **Static path:** `filepath="/data/input/orders.csv"`
2. **Jinja-templated path:** `filepath="/data/input/orders_{{ ds_nodash }}.csv"` — resolves to a date-based filename like `orders_20240115.csv`
3. **Glob wildcard pattern:** `filepath="/data/input/orders_*.csv"` — matches any file starting with `orders_`

When you use a glob pattern, `FileSensor` uses Python's `glob.glob()` internally and returns `True` as soon as **at least one** matching file exists.

```python
# Wait for a file named with today's date
FileSensor(filepath="/data/vendor/sales_{{ ds_nodash }}.csv", ...)

# Wait for ANY csv in today's subfolder
FileSensor(filepath="/data/incoming/{{ ds }}/*.csv", ...)
```

---

### Q3: What is `fs_conn_id` and do you always need it?

**Answer:**

`fs_conn_id` references an Airflow Connection of type `File (path)`. It tells `FileSensor` which filesystem base path to use.

For **local filesystem** access on the Airflow worker, the default `"fs_default"` connection works without any setup. For mounted network drives or remote paths, you configure a connection in **Admin → Connections** with type `File (path)` pointing to the base directory.

In practice, many teams omit explicit `fs_conn_id` setup when checking local or NFS-mounted paths, because `fs_default` maps to the worker's local filesystem and any absolute `filepath` works directly.

```python
# Most common: using default connection (local filesystem)
FileSensor(
    task_id="wait",
    filepath="/mnt/shared/data/file.csv",  # absolute path
    fs_conn_id="fs_default",
)
```

---

### Q4: What are `poke_interval` and `timeout`, and how do you choose values?

**Answer:**

- **`poke_interval`** (seconds, default `60`): how often `FileSensor` checks whether the file exists. Too low wastes resources; too high means you wait longer than necessary after the file arrives.
- **`timeout`** (seconds, default `604800` = 7 days): maximum time the sensor will wait before giving up and marking the task failed (or skipped if `soft_fail=True`).

**Choosing values:**

| Scenario | `poke_interval` | `timeout` |
|---|---|---|
| File expected within minutes | 30s | 30–60 min |
| Vendor file, arrives anytime before noon | 60s | 6–8 hours |
| File from overnight batch job | 120s | 3–4 hours |
| Slow external system | 300s | 12–24 hours |

**Never leave `timeout` at the 7-day default in production.** A stuck sensor running for days blocks downstream tasks and burns resources.

---

### Q5: What is `soft_fail` and when would you use it?

**Answer:**

`soft_fail=True` changes how `FileSensor` behaves when the timeout is exceeded:

- **`soft_fail=False` (default):** task is marked **failed** — alerts fire, retries may trigger, downstream tasks are blocked.
- **`soft_fail=True`:** task is marked **skipped** — no error cascade, but downstream tasks are also skipped unless they use `trigger_rule="none_failed"` or `trigger_rule="all_done"`.

**Use `soft_fail=True` when the file is optional** — for example, a "returns" file that only exists on days with customer returns. If no returns happened today, the file won't exist and that's fine.

```python
# Required file — hard fail if not delivered
FileSensor(task_id="wait_for_orders", filepath="/data/orders_{{ ds_nodash }}.csv",
           timeout=7200, soft_fail=False)

# Optional file — skip if not present
FileSensor(task_id="wait_for_returns", filepath="/data/returns_{{ ds_nodash }}.csv",
           timeout=3600, soft_fail=True)

# Downstream task handles both cases
merge_task = PythonOperator(
    task_id="merge",
    python_callable=merge_files,
    trigger_rule="none_failed",  # Runs even if returns sensor was skipped
)
```

---

## Intermediate Questions

### Q6: What is the difference between `poke` mode and `reschedule` mode?

**Answer:**

Both modes control the sensor's waiting behavior, but they differ critically in resource usage:

| Aspect | `poke` (default) | `reschedule` |
|---|---|---|
| Worker slot | **Held** for entire wait | **Released** between pokes |
| Worker process | Sleeps in a loop | Freed for other tasks |
| Best for | Short waits (< 2–3 min) | Waits of minutes or hours |
| Risk | Can fill up worker pool | Slight scheduling overhead |

In `reschedule` mode, the sensor pokes, finds the condition not met, records the last poke time, and then **releases its worker slot**. Airflow reschedules the task after `poke_interval` seconds. The worker is completely free in between.

**In production, always use `mode="reschedule"` for `FileSensor`** unless you expect the file to arrive in under a minute. Vendor files, batch outputs, and scheduled deliveries can take hours — holding a worker slot the entire time starves other tasks.

```python
# Production best practice
FileSensor(
    task_id="wait_for_file",
    filepath="/data/incoming/file_{{ ds_nodash }}.csv",
    mode="reschedule",   # Free the worker slot between checks
    poke_interval=120,
    timeout=6 * 60 * 60,
)
```

---

### Q7: How does FileSensor handle wildcard paths, and what happens after it succeeds?

**Answer:**

When `filepath` contains a glob wildcard (`*`, `?`, `[...]`), `FileSensor` calls `glob.glob(filepath)` internally. It returns `True` if the result list is non-empty (i.e., at least one matching file exists).

**Important:** `FileSensor` only tells you "at least one file matching this pattern exists." It does **not** return which file(s) matched. To find the actual files, use `glob.glob()` in your downstream Python task:

```python
wait_for_any_report = FileSensor(
    task_id="wait_for_any_report",
    filepath="/data/reports/{{ ds }}/report_*.xlsx",
    mode="reschedule",
    poke_interval=120,
    timeout=8 * 60 * 60,
)

def process_reports(**context):
    import glob
    pattern = f"/data/reports/{context['ds']}/report_*.xlsx"
    files = glob.glob(pattern)
    print(f"Found {len(files)} report(s): {files}")
    # process each file...

process = PythonOperator(task_id="process_reports", python_callable=process_reports)

wait_for_any_report >> process
```

---

### Q8: What happens when FileSensor times out?

**Answer:**

When the sensor's `timeout` is exceeded without the file appearing:

1. Airflow raises an `AirflowSensorTimeout` exception inside the sensor task.
2. The task state becomes **failed** (default, `soft_fail=False`) or **skipped** (`soft_fail=True`).
3. With failed state: `on_failure_callback` fires, email alerts send, downstream tasks are marked `upstream_failed`.
4. With skipped state: downstream tasks are also skipped unless they have a permissive `trigger_rule`.

**Diagnosing a timeout:** Check the task logs — the last log line before the timeout shows the last poke attempt and its result. Verify the filepath pattern, the connection, and whether the file actually exists on the worker's filesystem.

---

### Q9: How do you wait for multiple files before proceeding?

**Answer:**

Use multiple `FileSensor` tasks running **in parallel**, all pointing at different files. Then funnel into the next task using a list dependency:

```python
wait_for_sales = FileSensor(
    task_id="wait_for_sales",
    filepath="/data/incoming/sales_{{ ds_nodash }}.csv",
    mode="reschedule", poke_interval=60, timeout=7200,
)

wait_for_customers = FileSensor(
    task_id="wait_for_customers",
    filepath="/data/incoming/customers_{{ ds_nodash }}.csv",
    mode="reschedule", poke_interval=60, timeout=7200,
)

wait_for_products = FileSensor(
    task_id="wait_for_products",
    filepath="/data/incoming/products_{{ ds_nodash }}.csv",
    mode="reschedule", poke_interval=60, timeout=7200,
    soft_fail=True,  # Products file is optional
)

process_all = PythonOperator(
    task_id="process_all_files",
    python_callable=process,
    trigger_rule="none_failed",  # Handle optional products
)

[wait_for_sales, wait_for_customers, wait_for_products] >> process_all
```

The three sensors run in parallel. `process_all` runs once all three have finished (success or skip).

---

## Advanced Questions

### Q10: How does FileSensor compare to S3KeySensor?

**Answer:**

Both sensors wait for a file to exist, but they target different storage systems:

| Aspect | `FileSensor` | `S3KeySensor` |
|---|---|---|
| Storage target | Local/mounted filesystem | AWS S3 |
| Connection type | `fs_conn_id` (File path) | `aws_conn_id` (AWS) |
| Import | `airflow.sensors.filesystem` | `airflow.providers.amazon.aws.sensors.s3` |
| Wildcard support | Python `glob` patterns | `wildcard_match=True` |
| Multi-key check | Multiple sensors in parallel | Single sensor with `bucket_key=[list]` |
| Deferrable mode | No | Yes (`deferrable=True` in Airflow 3) |
| Use case | On-worker files, NFS mounts | Cloud data lake, vendor S3 drops |

For most modern cloud-based pipelines, `S3KeySensor` is more common. Use `FileSensor` for on-premises pipelines with network-mounted storage or legacy systems that write to local paths.

---

### Q11: What is `exponential_backoff` and when should you use it?

**Answer:**

When `exponential_backoff=True`, `FileSensor` increases the wait time between pokes exponentially rather than using a fixed `poke_interval`. This is useful when:

- The file's arrival time is uncertain and highly variable
- You want to check frequently early on (in case the file arrives quickly) but check less often later (to save resources during long waits)
- You need to reduce load on the filesystem during busy periods

```python
FileSensor(
    task_id="wait_with_backoff",
    filepath="/data/incoming/report_{{ ds_nodash }}.csv",
    poke_interval=30,           # Start checking every 30 seconds
    exponential_backoff=True,   # Each poke doubles the wait: 30s, 60s, 120s, 240s...
    timeout=3 * 60 * 60,
    mode="reschedule",
)
```

**Caution:** With exponential backoff, after many pokes the interval can become very long. If the file arrives late, you might wait significantly longer than `poke_interval` before the sensor detects it. Use it when early detection matters more than late detection.

---

### Q12: A FileSensor keeps timing out even though the file exists. What would you investigate?

**Answer:**

This is a classic debugging scenario. Work through these checks in order:

1. **Worker filesystem visibility:** The sensor runs on the Airflow worker, not the scheduler. Is the file accessible from the **worker's** perspective? NFS mounts might be mounted on the scheduler host but not the worker.

2. **Permissions:** Does the Airflow worker process have read permission on the directory? Run `os.path.exists(path)` or `ls -la /path/` as the airflow OS user.

3. **Filepath template rendering:** Print the resolved `filepath` in task logs. A Jinja template with the wrong date format could produce `/data/incoming/orders_2024-01-15.csv` when the file is named `orders_20240115.csv` (no dashes).

4. **Glob pattern escaping:** Special characters in directory names can break glob. Test the pattern manually with `glob.glob(pattern)`.

5. **fs_conn_id base path:** If your connection has a `path` set, `FileSensor` may be prepending it to your `filepath`. Check the connection configuration in Admin → Connections.

6. **Timing:** Add a `print` statement or check task logs — are pokes actually executing? A rescheduled sensor might not be re-queued if the scheduler is overloaded.

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [Sensors Overview](../Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [HttpSensor](../02_HttpSensor/Theory.md)
