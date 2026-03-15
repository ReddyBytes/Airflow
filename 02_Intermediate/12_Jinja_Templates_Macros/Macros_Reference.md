# Airflow 3 Macros — Complete Reference

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## How to Read This Reference

Every macro below is available inside any operator field that is listed in `template_fields`. Access them with `{{ macro_name }}` syntax in your operator arguments.

Macros that are objects (like `data_interval_start`) let you call their methods and attributes using dot notation: `{{ data_interval_start.year }}`.

---

## Section 1: Date/Time String Macros

### `ds`

| Property | Value |
|---|---|
| **Type** | `str` |
| **Example Value** | `2025-03-15` |
| **Format** | `YYYY-MM-DD` |
| **Description** | The start of the data interval formatted as an ISO date string. This is the single most commonly used macro in Airflow. |
| **When to Use** | SQL `WHERE dt = '{{ ds }}'`, file names `sales_{{ ds }}.csv`, S3 keys, API request parameters. |

```python
bash_command = "load.py --date {{ ds }}"
```

---

### `ds_nodash`

| Property | Value |
|---|---|
| **Type** | `str` |
| **Example Value** | `20250315` |
| **Format** | `YYYYMMDD` |
| **Description** | Same as `ds` but with hyphens removed. |
| **When to Use** | Hive partition values (`dt=20250315`), systems that reject hyphens in identifiers, compact directory names. |

```python
bash_command = "hive -e 'MSCK REPAIR TABLE t PARTITION (dt={{ ds_nodash }})'"
```

---

### `ts`

| Property | Value |
|---|---|
| **Type** | `str` |
| **Example Value** | `2025-03-15T00:00:00+00:00` |
| **Format** | ISO 8601 with timezone |
| **Description** | Full timestamp of the data interval start. Includes time component and UTC offset. |
| **When to Use** | APIs that require a full datetime, log messages that need precision, audit records. |

```python
bash_command = "echo 'Run timestamp: {{ ts }}'"
```

---

### `ts_nodash`

| Property | Value |
|---|---|
| **Type** | `str` |
| **Example Value** | `20250315T000000+0000` |
| **Format** | Compact ISO 8601 — no separators |
| **Description** | Full timestamp with all separators removed. Sortable and filesystem-safe. |
| **When to Use** | Archive filenames that must sort chronologically, object storage keys where colons are invalid. |

```python
bash_command = "cp result.csv /archive/result_{{ ts_nodash }}.csv"
```

---

### `ts_nodash_with_tz`

| Property | Value |
|---|---|
| **Type** | `str` |
| **Example Value** | `20250315T000000+0000` |
| **Format** | Same as `ts_nodash` |
| **Description** | Alias for `ts_nodash`. Retained for compatibility. |
| **When to Use** | Same as `ts_nodash`. |

---

## Section 2: DateTime Object Macros

These macros return `pendulum.DateTime` objects. You can call pendulum methods on them directly in Jinja templates.

### `data_interval_start`

| Property | Value |
|---|---|
| **Type** | `pendulum.DateTime` |
| **Example Value** | `2025-03-15T00:00:00+00:00` |
| **Description** | The **start** of the scheduled data interval. This is the Airflow 3 canonical macro for "when does this batch's data begin." Replaces the deprecated `execution_date`. |
| **When to Use** | Any time you need the full datetime object — month/year extraction, custom formatting, arithmetic via pendulum methods. |

```python
# Extract year and month for partitioning
s3_key = "data/{{ data_interval_start.year }}/{{ '%02d' % data_interval_start.month }}/"

# Custom format
bash_command = "report.py --month {{ data_interval_start.strftime('%B %Y') }}"
# Renders to: report.py --month March 2025
```

**Useful pendulum attributes and methods:**

| Expression | Output |
|---|---|
| `{{ data_interval_start.year }}` | `2025` |
| `{{ data_interval_start.month }}` | `3` |
| `{{ data_interval_start.day }}` | `15` |
| `{{ data_interval_start.hour }}` | `0` |
| `{{ data_interval_start.isoformat() }}` | `2025-03-15T00:00:00+00:00` |
| `{{ data_interval_start.to_date_string() }}` | `2025-03-15` |
| `{{ data_interval_start.strftime('%d/%m/%Y') }}` | `15/03/2025` |
| `{{ data_interval_start.day_of_week }}` | `5` (0=Monday) |
| `{{ data_interval_start.week_of_year }}` | `11` |
| `{{ data_interval_start.start_of('month').to_date_string() }}` | `2025-03-01` |
| `{{ data_interval_start.end_of('month').to_date_string() }}` | `2025-03-31` |
| `{{ data_interval_start.add(days=7).to_date_string() }}` | `2025-03-22` |
| `{{ data_interval_start.subtract(months=1).to_date_string() }}` | `2025-02-15` |

---

### `data_interval_end`

| Property | Value |
|---|---|
| **Type** | `pendulum.DateTime` |
| **Example Value** | `2025-03-16T00:00:00+00:00` |
| **Description** | The **end** of the scheduled data interval. For a `@daily` DAG, `data_interval_start` is midnight at the start of the day and `data_interval_end` is midnight at the start of the next day. |
| **When to Use** | When specifying the end boundary of a data fetch. Pair with `data_interval_start` for explicit range queries. |

```python
bash_command = (
    "fetch.py "
    "--from {{ data_interval_start.isoformat() }} "
    "--to   {{ data_interval_end.isoformat() }}"
)
```

---

### `logical_date`

| Property | Value |
|---|---|
| **Type** | `pendulum.DateTime` |
| **Example Value** | `2025-03-15T00:00:00+00:00` |
| **Description** | Identical to `data_interval_start`. Kept as a named alias to ease migration from Airflow 2.x where it was called `execution_date`. |
| **When to Use** | Migrating old DAGs that used `{{ execution_date }}`. New code should use `data_interval_start`. |

---

### `next_ds`

| Property | Value |
|---|---|
| **Type** | `str` |
| **Example Value** | `2025-03-16` |
| **Format** | `YYYY-MM-DD` |
| **Description** | The `data_interval_end` formatted as a date string. Equivalent to `ds` of the next scheduled run. |
| **When to Use** | When you need the end boundary as a plain date string (no time component). |

```python
bash_command = "query.py --start {{ ds }} --end {{ next_ds }}"
```

---

### `next_ds_nodash`

| Property | Value |
|---|---|
| **Type** | `str` |
| **Example Value** | `20250316` |
| **Format** | `YYYYMMDD` |
| **Description** | `next_ds` without hyphens. |
| **When to Use** | Same as `next_ds` but for systems that forbid dashes. |

---

## Section 3: Previous Run Macros

### `prev_data_interval_start_success`

| Property | Value |
|---|---|
| **Type** | `pendulum.DateTime \| None` |
| **Example Value** | `2025-03-14T00:00:00+00:00` |
| **Description** | The `data_interval_start` of the most recent DAG run that **completed successfully**. Returns `None` if no prior successful run exists (i.e., on the first run). |
| **When to Use** | Incremental ETL: "load all records that arrived since the last time we ran successfully." |

```python
bash_command = (
    "incremental.py "
    "--since {{ prev_data_interval_start_success or '2020-01-01' }}"
)
```

---

### `prev_data_interval_end_success`

| Property | Value |
|---|---|
| **Type** | `pendulum.DateTime \| None` |
| **Example Value** | `2025-03-15T00:00:00+00:00` |
| **Description** | The `data_interval_end` of the most recent successful run. Use this to avoid gaps or overlaps between consecutive incremental loads. |
| **When to Use** | "Load from where the last successful run ended, up to the current interval end." |

```python
bash_command = (
    "load.py "
    "--from {{ prev_data_interval_end_success or '2020-01-01' }} "
    "--to {{ data_interval_end }}"
)
```

---

### `prev_start_date_success`

| Property | Value |
|---|---|
| **Type** | `pendulum.DateTime \| None` |
| **Example Value** | `2025-03-14T00:01:05+00:00` |
| **Description** | The actual *wall-clock* start time of the most recent successful run (not the data interval start). Rarely needed; prefer `prev_data_interval_start_success`. |
| **When to Use** | Debugging or SLA monitoring where you care about actual execution time, not data time. |

---

## Section 4: Run & Task Metadata Macros

### `dag_run`

| Property | Value |
|---|---|
| **Type** | `DagRun` object |
| **Description** | The full `DagRun` model instance for the current run. |
| **When to Use** | Accessing `run_id`, `conf`, `run_type`, `external_trigger`. |

**Key attributes:**

| Attribute | Type | Example | Description |
|---|---|---|---|
| `dag_run.run_id` | `str` | `scheduled__2025-03-15T00:00:00+00:00` | Unique identifier for this run |
| `dag_run.conf` | `dict` | `{"env": "prod"}` | Config passed at manual trigger |
| `dag_run.run_type` | `str` | `scheduled` or `manual` | How the run was triggered |
| `dag_run.external_trigger` | `bool` | `False` | Was this triggered externally? |
| `dag_run.dag_id` | `str` | `my_dag` | Name of the DAG |

```python
bash_command = (
    "echo 'Run: {{ dag_run.run_id }}' && "
    "echo 'Target: {{ dag_run.conf.get(\"table\", \"default\") }}'"
)
```

---

### `task`

| Property | Value |
|---|---|
| **Type** | `BaseOperator` object |
| **Description** | The operator instance for the currently executing task. |
| **When to Use** | Accessing task metadata like `task_id`, `dag_id`, `owner`, `retries`. |

**Key attributes:**

| Attribute | Type | Example |
|---|---|---|
| `task.task_id` | `str` | `process_data` |
| `task.dag_id` | `str` | `daily_etl` |
| `task.owner` | `str` | `data-team` |
| `task.retries` | `int` | `3` |
| `task.upstream_task_ids` | `set` | `{'extract', 'validate'}` |
| `task.downstream_task_ids` | `set` | `{'notify'}` |

---

### `ti` / `task_instance`

| Property | Value |
|---|---|
| **Type** | `TaskInstance` object |
| **Description** | The `TaskInstance` object combining task definition with specific run. Both `ti` and `task_instance` refer to the same object. |
| **When to Use** | Try number, XCom access, task state, hostname. |

**Key attributes:**

| Attribute | Type | Example | Description |
|---|---|---|---|
| `ti.task_id` | `str` | `my_task` | Task identifier |
| `ti.dag_id` | `str` | `my_dag` | DAG identifier |
| `ti.run_id` | `str` | `scheduled__2025-03-15T00:00:00+00:00` | Run identifier |
| `ti.try_number` | `int` | `1` | Current attempt (1-based) |
| `ti.max_tries` | `int` | `3` | Max retries configured |
| `ti.hostname` | `str` | `worker-1.example.com` | Worker executing the task |
| `ti.state` | `str` | `running` | Current task state |

```python
bash_command = "echo 'Attempt {{ ti.try_number }} of {{ ti.max_tries + 1 }}'"
```

---

### `params`

| Property | Value |
|---|---|
| **Type** | `ParamsDict` |
| **Description** | The resolved parameter values for this run. Defined on the DAG using `Param` objects; can be overridden at trigger time. |
| **When to Use** | Any dynamic value that an operator needs that comes from the DAG definition or trigger-time input. |

```python
# Definition
params = {
    "environment": Param("production", type="string"),
    "max_rows": Param(10000, type="integer"),
}

# Usage in template
bash_command = "etl.py --env {{ params.environment }} --limit {{ params.max_rows }}"
```

---

## Section 5: `macros.*` Helper Functions

### `macros.ds_add(ds, days)`

| Property | Value |
|---|---|
| **Signature** | `(ds: str, days: int) -> str` |
| **Returns** | `YYYY-MM-DD` string |
| **Description** | Adds `days` to `ds`. Negative values subtract. |

```python
{{ macros.ds_add(ds, -7) }}   # One week ago
{{ macros.ds_add(ds, 1) }}    # Tomorrow
{{ macros.ds_add(ds, -30) }}  # Approximately one month ago
```

---

### `macros.ds_format(ds, from_fmt, to_fmt)`

| Property | Value |
|---|---|
| **Signature** | `(ds: str, from_fmt: str, to_fmt: str) -> str` |
| **Returns** | Date string in `to_fmt` format |
| **Description** | Parses `ds` using `from_fmt` (strptime syntax) and returns it formatted as `to_fmt` (strftime syntax). |

```python
{{ macros.ds_format(ds, '%Y-%m-%d', '%d/%m/%Y') }}   # 15/03/2025
{{ macros.ds_format(ds, '%Y-%m-%d', '%B %d, %Y') }}  # March 15, 2025
{{ macros.ds_format(ds, '%Y-%m-%d', '%Y%m') }}        # 202503 (year-month only)
```

---

### `macros.datetime`

Python's `datetime.datetime` class. Lets you construct specific datetime objects inside templates.

```python
{{ macros.datetime(2025, 1, 1) }}
{{ (data_interval_start - macros.datetime(2025, 1, 1, tzinfo=macros.dateutil.tz.UTC)).days }}
```

---

### `macros.timedelta`

Python's `datetime.timedelta` class.

```python
{{ (data_interval_start - macros.timedelta(days=7)).to_date_string() }}
```

---

### `macros.dateutil`

The full `dateutil` library. Useful for relative deltas (add months, add years).

```python
{{ (data_interval_start + macros.dateutil.relativedelta.relativedelta(months=-1)).to_date_string() }}
# One month ago: 2025-02-15
```

---

### `macros.uuid`

Python's `uuid` module. Useful for generating unique identifiers inside templates.

```python
bash_command = "run_job.py --job-id {{ macros.uuid.uuid4() }}"
```

---

### `macros.random`

Python's `random` module.

```python
bash_command = "test.py --seed {{ macros.random.randint(1, 99999) }}"
```

---

### `macros.time`

Python's `time` module.

```python
bash_command = "echo 'Epoch: {{ macros.time.time() }}'"
```

---

### `macros.json`

Python's `json` module. Useful for serializing dicts or lists inside template strings.

```python
bash_command = "process.py --config '{{ macros.json.dumps(dag_run.conf) }}'"
```

---

## Section 6: Context Variables Available in Python Tasks

When using `@task` or accessing `**context`, all macros are available as dictionary keys:

```python
@task
def my_task(**context):
    ds                              = context["ds"]
    ds_nodash                       = context["ds_nodash"]
    ts                              = context["ts"]
    data_interval_start             = context["data_interval_start"]
    data_interval_end               = context["data_interval_end"]
    logical_date                    = context["logical_date"]
    dag_run                         = context["dag_run"]
    ti                              = context["ti"]
    params                          = context["params"]
    prev_start_success              = context["prev_data_interval_start_success"]
```

---

## Section 7: Deprecation Notice (Airflow 3)

The following macros from Airflow 1.x / 2.x are **removed or deprecated** in Airflow 3:

| Old Macro | Status in Airflow 3 | Replacement |
|---|---|---|
| `execution_date` | **Removed** | `data_interval_start` or `logical_date` |
| `next_execution_date` | **Removed** | `data_interval_end` |
| `prev_execution_date` | **Removed** | `prev_data_interval_start_success` |
| `prev_execution_date_success` | **Removed** | `prev_data_interval_start_success` |
| `tomorrow_ds` | Deprecated | `next_ds` |
| `yesterday_ds` | Deprecated | `macros.ds_add(ds, -1)` |
