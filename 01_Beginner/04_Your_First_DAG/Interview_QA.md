# 03 · DAGs Deep Dive — Interview Q&A

12 questions covering DAG fundamentals, scheduling behavior, and best practices.

---

### Q1. What is catchup and when should you disable it?

**Answer:**

Catchup is a DAG parameter that controls whether Airflow should create DAG Runs for all missed schedule intervals between `start_date` and the current date.

When `catchup=True` (the default):
- If `start_date` is `2024-01-01` and today is `2024-01-10`, Airflow sees 9 missed daily intervals and creates 9 DAG Runs immediately when the DAG is first loaded.

When `catchup=False`:
- Airflow ignores historical intervals and only runs going forward from the current time.

**When to keep `catchup=True`:**
- Building a data pipeline that needs to process historical records from `start_date`
- Doing a planned backfill after a code fix
- Your pipeline is idempotent and you genuinely want all historical intervals processed

**When to set `catchup=False`:**
- Most new DAGs — you just want it to run going forward
- Alerting or notification DAGs — you do not want 100 old alerts sent at once
- Any DAG where running historical intervals would cause side effects

Best practice: set `catchup=False` by default in `default_args` or in `airflow.cfg` and explicitly enable it only when needed.

---

### Q2. What is the difference between a DAG Run and a Task Instance?

**Answer:**

A **DAG Run** represents one complete execution of a DAG for a specific `logical_date`. It has a state (`running`, `success`, `failed`) that reflects the overall status of all its tasks.

A **Task Instance** represents one execution of a specific task within a specific DAG Run. A DAG with 5 tasks has 5 Task Instances per DAG Run.

Relationship:
- 1 DAG Run contains N Task Instances (where N = number of tasks in the DAG)
- 1 DAG contains M DAG Runs over time (one per scheduled interval)
- The Metadata Database stores every Task Instance with its start time, end time, state, and log location

In the Airflow UI:
- The **Grid view** shows DAG Runs as columns and tasks as rows — each cell is a Task Instance
- Clicking a cell shows the Task Instance details and lets you view logs, clear the task, or mark it as success

---

### Q3. How does `schedule_interval` work? When exactly does a DAG run?

**Answer:**

This is a major source of confusion for Airflow beginners.

The rule: **a DAG run triggers at the END of the interval it covers, not the start**.

Example:
- `start_date = 2024-01-01`
- `schedule_interval = "@daily"` (runs at midnight)
- The first run happens at **2024-01-02 00:00** (midnight between Jan 1 and Jan 2)
- That run has `logical_date = 2024-01-01` (the start of the interval it covers)

Why? Airflow was designed for batch data processing. The idea is: "the run for January 1st processes data that was generated during January 1st. It can only run after January 1st is complete."

Another example with `schedule_interval = "0 6 * * *"` (6am daily):
- `start_date = 2024-01-01`
- First run triggers at **2024-01-02 06:00**
- `logical_date = 2024-01-01 06:00`

**In templates:**
- `{{ ds }}` gives the logical date in `YYYY-MM-DD` format
- This is the date the run is "about", not the date it ran

---

### Q4. What is `start_date` and what are the rules for setting it?

**Answer:**

`start_date` is the date from which Airflow begins calculating schedule intervals. The first run covers the interval that starts at `start_date`.

**Rules:**

1. **Must be a fixed datetime, not `datetime.now()`**
   The DAG file is parsed every 30 seconds. If `start_date = datetime.now()`, the value changes on every parse, causing Airflow to constantly recalculate what runs are due and create duplicate or missing runs.

   ```python
   # WRONG
   start_date=datetime.now()

   # CORRECT
   start_date=datetime(2024, 1, 1)
   ```

2. **Set it in the past**
   It is fine (and normal) for `start_date` to be months or years in the past. Combined with `catchup=False`, Airflow simply ignores the historical intervals.

3. **Timezone awareness**
   If your Airflow is configured with a timezone (recommended), make your `start_date` timezone-aware:
   ```python
   from pendulum import datetime
   start_date=datetime(2024, 1, 1, tz="UTC")
   ```

4. **`start_date` in `default_args` vs in `DAG()`**
   You can set it in either place. Setting it in `DAG()` directly is clearer. If set in both, the one in `DAG()` takes precedence.

---

### Q5. How do you trigger a DAG run manually?

**Answer:**

**Via the UI:**
1. Find the DAG in the DAGs list
2. Click the Play button (triangle icon) on the right side of the row
3. Optionally provide a JSON config for the run (accessed via `{{ dag_run.conf }}` in templates)
4. Click "Trigger"

**Via the CLI:**
```bash
# Basic trigger
airflow dags trigger my_dag_id

# Trigger with a specific logical date
airflow dags trigger my_dag_id --execution-date 2024-01-15

# Trigger with a JSON config
airflow dags trigger my_dag_id --conf '{"key": "value"}'
```

**Via the REST API:**
```bash
curl -X POST http://localhost:8080/api/v1/dags/my_dag_id/dagRuns \
  -H "Content-Type: application/json" \
  -u airflow:airflow \
  -d '{"logical_date": "2024-01-15T00:00:00Z"}'
```

A manually triggered run gets a `run_id` starting with `manual__` (e.g., `manual__2024-01-15T00:00:00+00:00`). Scheduled runs get `scheduled__` prefix.

---

### Q6. What is idempotency in the context of Airflow tasks?

**Answer:**

An idempotent task is one that can be run multiple times and always produces the same result. Running it once or ten times is equivalent.

This matters in Airflow because:
1. Tasks are retried automatically on failure — the same task code runs again from the beginning
2. You can manually clear and re-run tasks at any time
3. Backfills re-run historical tasks

**Non-idempotent example (dangerous):**
```python
# Every run appends rows — re-running doubles the data
def load():
    execute_sql("INSERT INTO sales_daily SELECT * FROM staging")
```

**Idempotent version:**
```python
# Delete today's data first, then insert — re-running is safe
def load(**context):
    logical_date = context["ds"]
    execute_sql(f"""
        DELETE FROM sales_daily WHERE date = '{logical_date}';
        INSERT INTO sales_daily SELECT * FROM staging WHERE date = '{logical_date}';
    """)
```

Other patterns for idempotency:
- Upserts: `INSERT ... ON CONFLICT (id) DO UPDATE SET ...`
- Write to a date-partitioned location: `/data/2024-01-15/output.parquet` (overwrite is safe)
- Atomic file writes: write to temp path, then rename

---

### Q7. What does `depends_on_past` do?

**Answer:**

When `depends_on_past=True` is set on a task, that task will not run unless the same task in the **previous DAG Run** completed successfully.

Example:
- DAG runs daily
- Task `transform` has `depends_on_past=True`
- January 2nd's `transform` task will not start until January 1st's `transform` task has `success` state

This creates a serial dependency across runs, not just within a run.

**When to use it:**
- When your task is stateful and requires the previous run's output to exist
- When you are doing incremental processing where each run builds on the last
- When running two overlapping runs simultaneously would cause a conflict

**Caution:**
- If a task fails and `depends_on_past=True`, all future runs of that task are blocked until you manually mark the failed instance as success or clear it.
- This can cause a silent backlog if not monitored.

---

### Q8. How does Airflow handle failed tasks?

**Answer:**

Airflow has a layered failure handling system:

**1. Automatic retries**
If `retries > 0` in `default_args` or on the task, the task is marked `up_for_retry` and re-queued after `retry_delay`. Retries use the same task instance but increment the attempt number.

**2. Upstream failure propagation**
If task A fails and task B depends on A, task B is marked `upstream_failed` and does not run (unless `TriggerRule.ALL_DONE` or similar is set — see Section 10).

**3. DAG Run state**
A DAG Run is marked `failed` if any task reaches the `failed` state with no retries left.

**4. Callbacks**
- `on_failure_callback` on a task: called when that specific task fails (after all retries)
- `on_failure_callback` on the DAG: called when the DAG Run fails
- `email_on_failure=True`: sends an email alert

**5. Manual recovery**
Via the UI, you can:
- **Clear** a failed task — resets it to `none` so the Scheduler re-runs it
- **Mark as success** — manually override the state (useful if you fixed the issue externally)
- **Clear downstream** — clears the failed task and all its dependents

**6. SLA misses**
If `sla` is set on a task and the task does not complete within that time, Airflow logs an SLA miss and can call an `sla_miss_callback`.

---

### Q9. What is the difference between `execution_date` and `logical_date`?

**Answer:**

These refer to the same concept but `logical_date` is the modern (Airflow 2.2+) name for what was called `execution_date`.

Both represent: **the start of the schedule interval that the DAG Run covers**.

- For a daily DAG with `start_date=2024-01-01`, the first run has `logical_date=2024-01-01`
- That run is actually triggered on `2024-01-02` (the day after), but its logical date is Jan 1st

**Why renamed?**
`execution_date` was confusing because it is NOT the date the task executes — it is the date the interval starts. `logical_date` is more accurate.

In templates, use `{{ ds }}` (renders as `YYYY-MM-DD`) or `{{ logical_date }}` (renders as ISO timestamp).

In Python code inside tasks:
```python
def my_task(**context):
    logical_date = context["logical_date"]  # pendulum.DateTime object
    ds = context["ds"]                      # string "YYYY-MM-DD"
```

For backward compatibility, `execution_date` still works but triggers a deprecation warning.

---

### Q10. How do you parametrize a DAG run at trigger time?

**Answer:**

Use the `conf` parameter when triggering a DAG run. This passes a JSON dict that is accessible via `dag_run.conf` inside the run.

**Triggering with config:**
```bash
airflow dags trigger my_dag --conf '{"target_table": "sales", "date": "2024-01-15"}'
```

**Accessing config inside a task:**
```python
def my_task(**context):
    conf = context["dag_run"].conf or {}
    table = conf.get("target_table", "default_table")
    print(f"Processing table: {table}")
```

**In Jinja templates:**
```bash
# In a BashOperator
bash_command="echo {{ dag_run.conf.get('target_table', 'default') }}"
```

**For production parametrization**, use Airflow Variables (Section 08) for values that change between environments, and `dag_run.conf` for values that change between individual runs.

---

### Q11. What happens if two DAG files define the same `dag_id`?

**Answer:**

Airflow uses `dag_id` as the unique identifier for a DAG. If two files both define a DAG with the same `dag_id`, the behavior is non-deterministic — whichever file is parsed last "wins" and its definition is stored in the Metadata Database.

This results in:
- Unpredictable task definitions (the DAG might switch between two different task structures)
- Confusing UI behavior
- Potential for run history to be associated with the wrong definition

**How to detect this:**
- The Scheduler logs will show a warning about duplicate DAG IDs
- The `Import Errors` section in the Airflow UI may surface this

**Best practices:**
- Use descriptive, namespaced `dag_id` values: `team_product_pipeline_v2`, not just `etl`
- Use a naming convention like `{team}_{domain}_{frequency}`: `data_sales_daily`
- Enforce uniqueness with a CI/CD check that scans all DAG files for duplicate IDs

---

### Q12. How do you make a DAG run only once?

**Answer:**

Two options:

**Option 1: `schedule_interval=None`**
The DAG never runs on a schedule. It only runs when triggered manually (UI, CLI, or API).

```python
with DAG(
    dag_id="one_time_migration",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
) as dag:
    ...
```

**Option 2: `schedule_interval="@once"`**
The DAG runs exactly once automatically — at the first scheduled time after `start_date`. After that, it creates no more runs.

```python
with DAG(
    dag_id="one_time_setup",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@once",
    catchup=False,
) as dag:
    ...
```

**Difference:**
- `None`: runs zero times unless manually triggered. You decide when.
- `@once`: runs exactly once automatically. Airflow decides when (right after `start_date`).

For one-time migrations or setup scripts, `@once` is useful. For pipelines that should only run when explicitly requested (like on-demand reports), use `None`.

---

## 📂 Navigation

⬅️ **Prev:** [Cheatsheet](./Cheatsheet.md) | 🏠 **[Home](../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [Code Example](./Code_Example.md)
