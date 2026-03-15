# Jinja Templates & Macros — Cheatsheet

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Interview Q&A](./Interview_QA.md)**

---

## Built-In Macros Quick Reference

| Macro | Type | Example Output | Best Use Case |
|---|---|---|---|
| `{{ ds }}` | `str` | `2025-03-15` | File names, SQL WHERE clauses, partition keys |
| `{{ ds_nodash }}` | `str` | `20250315` | Hive partitions, paths that forbid dashes |
| `{{ ts }}` | `str` | `2025-03-15T00:00:00+00:00` | Logging, precise time-based APIs |
| `{{ ts_nodash }}` | `str` | `20250315T000000+0000` | Sortable, filesystem-safe filenames |
| `{{ ts_nodash_with_tz }}` | `str` | `20250315T000000+0000` | Same as ts_nodash with tz suffix |
| `{{ data_interval_start }}` | `pendulum.DateTime` | `2025-03-15T00:00:00+00:00` | Interval boundaries, method calls |
| `{{ data_interval_end }}` | `pendulum.DateTime` | `2025-03-16T00:00:00+00:00` | End of batch window |
| `{{ logical_date }}` | `pendulum.DateTime` | `2025-03-15T00:00:00+00:00` | Legacy compatibility (= execution_date) |
| `{{ prev_data_interval_start_success }}` | `pendulum.DateTime \| None` | `2025-03-14T00:00:00+00:00` | Incremental loads since last success |
| `{{ prev_data_interval_end_success }}` | `pendulum.DateTime \| None` | `2025-03-15T00:00:00+00:00` | No-gap incremental loads |
| `{{ dag_run.run_id }}` | `str` | `scheduled__2025-03-15T00:00:00+00:00` | Unique run identifiers, audit trails |
| `{{ dag_run.conf }}` | `dict` | `{"env": "prod"}` | Runtime config passed at trigger |
| `{{ task.task_id }}` | `str` | `my_task` | Task metadata in logs or outputs |
| `{{ task.dag_id }}` | `str` | `my_dag` | DAG name in outputs |
| `{{ ti.try_number }}` | `int` | `1` | Retry-aware behavior |
| `{{ ti.run_id }}` | `str` | `scheduled__2025-03-15T00:00:00+00:00` | Same as dag_run.run_id |
| `{{ params.my_param }}` | any | depends on definition | Typed, overridable runtime params |

---

## `macros.*` Helper Functions

| Function | Signature | Example | Output |
|---|---|---|---|
| `macros.ds_add` | `(ds: str, days: int) -> str` | `macros.ds_add(ds, -7)` | `2025-03-08` |
| `macros.ds_format` | `(ds: str, from_fmt: str, to_fmt: str) -> str` | `macros.ds_format(ds, '%Y-%m-%d', '%d/%m/%Y')` | `15/03/2025` |
| `macros.datetime` | Python `datetime` class | `macros.datetime(2025, 1, 1)` | datetime object |
| `macros.timedelta` | Python `timedelta` class | `macros.timedelta(days=7)` | timedelta object |
| `macros.dateutil` | `dateutil` library | `macros.dateutil.relativedelta.relativedelta(months=1)` | relativedelta |
| `macros.uuid` | `uuid` module | `macros.uuid.uuid4()` | UUID string |
| `macros.random` | `random` module | `macros.random.randint(1, 100)` | int |
| `macros.time` | `time` module | `macros.time.time()` | epoch float |
| `macros.json` | `json` module | `macros.json.dumps({"k": "v"})` | JSON string |

---

## `pendulum.DateTime` Methods (usable on `data_interval_start` etc.)

| Method / Attribute | Example | Output |
|---|---|---|
| `.year` | `{{ data_interval_start.year }}` | `2025` |
| `.month` | `{{ data_interval_start.month }}` | `3` |
| `.day` | `{{ data_interval_start.day }}` | `15` |
| `.strftime(fmt)` | `{{ data_interval_start.strftime('%Y/%m/%d') }}` | `2025/03/15` |
| `.isoformat()` | `{{ data_interval_start.isoformat() }}` | `2025-03-15T00:00:00+00:00` |
| `.to_date_string()` | `{{ data_interval_start.to_date_string() }}` | `2025-03-15` |
| `.day_of_week` | `{{ data_interval_start.day_of_week }}` | `5` (0=Mon) |
| `.add(days=7)` | `{{ data_interval_start.add(days=7) }}` | Next week DateTime |

---

## `template_fields` — Which Operators Support What

| Operator | `template_fields` |
|---|---|
| `BashOperator` | `bash_command`, `env` |
| `PythonOperator` | `templates_dict`, `op_args`, `op_kwargs` |
| `EmailOperator` | `to`, `subject`, `html_content` |
| `SimpleHttpOperator` / `HttpOperator` | `endpoint`, `data`, `headers` |
| `S3CopyObjectOperator` | `source_bucket_key`, `dest_bucket_key` |
| `BigQueryInsertJobOperator` | `configuration`, `job_id` |
| `SparkSubmitOperator` | `application`, `conf`, `env_vars` |

To check any operator:
```python
print(MyOperator.template_fields)
```

---

## Syntax Quick Reference

```
{{ variable }}              — output a value
{% if condition %}...{% endif %}   — conditional block
{% for item in list %}...{% endfor %} — loop
{{ value | default('fallback') }}  — Jinja filter with default
{{ value | upper }}         — uppercase filter
{{ dag_run.conf.get('key', 'default') }} — safe dict access
```

---

## Custom Macro Registration (Plugin)

```python
# plugins/my_macros.py
from airflow.plugins_manager import AirflowPlugin

def fiscal_quarter(ds: str) -> str:
    from datetime import date
    d = date.fromisoformat(ds)
    return f"Q{(d.month - 1) // 3 + 1}"

class MyMacrosPlugin(AirflowPlugin):
    name = "my_macros_plugin"
    macros = [fiscal_quarter]  # list of callables
```

Usage: `{{ macros.fiscal_quarter(ds) }}`

---

## Common Date Manipulation Patterns

```python
# Yesterday
{{ macros.ds_add(ds, -1) }}

# 7 days ago (rolling week)
{{ macros.ds_add(ds, -7) }}

# 30 days ago (rolling month)
{{ macros.ds_add(ds, -30) }}

# First day of current month
{{ data_interval_start.start_of('month').to_date_string() }}

# ISO week number
{{ data_interval_start.week_of_year }}

# Reformat to US date style
{{ macros.ds_format(ds, '%Y-%m-%d', '%m/%d/%Y') }}

# Partitioned path (Hive style)
year={{ data_interval_start.year }}/month={{ '%02d' % data_interval_start.month }}/day={{ '%02d' % data_interval_start.day }}

# Safe conf access with default
{{ dag_run.conf.get('table', 'orders') }}
```

---

## Key Rules to Remember

1. Jinja renders **only** fields listed in `template_fields`.
2. Inside `@task` Python functions, use `context["ds"]` — not `{{ ds }}`.
3. `data_interval_start` is a **pendulum object** — you can call `.year`, `.month`, `.strftime()` etc.
4. `prev_data_interval_start_success` can be `None` on the first run — always provide a fallback.
5. `dag_run.conf` is set only for **manually triggered** runs unless you set `params` as defaults.
6. Custom macros must be placed in the `plugins/` directory and registered via `AirflowPlugin`.
