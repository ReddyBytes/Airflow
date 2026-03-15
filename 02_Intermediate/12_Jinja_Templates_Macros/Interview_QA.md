# Jinja Templates & Macros — Interview Q&A

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Macros Reference](./Macros_Reference.md)**

---

## Q1: What is Jinja templating in Apache Airflow and why is it useful?

**Answer:**

Jinja templating is Airflow's mechanism for injecting runtime context values — like dates, run IDs, and parameters — into operator fields before a task executes. Airflow uses the Jinja2 engine to scan specific fields of an operator (those listed in `template_fields`) and replace any `{{ expression }}` patterns with their computed values.

It is useful because it eliminates hardcoded dates and configuration values from your DAG code. Instead of writing `"sales_2025-03-15.csv"`, you write `"sales_{{ ds }}.csv"`, and Airflow automatically substitutes the correct date for every run. This makes DAGs reusable, self-scheduling, and free from manual intervention.

---

## Q2: What is the difference between `ds` and `logical_date`?

**Answer:**

Both refer to the same underlying point in time — the start of the data interval — but they differ in type:

- `ds` is a **string** formatted as `YYYY-MM-DD` (e.g. `"2025-03-15"`). It is convenient for embedding in shell commands, file paths, and SQL queries.
- `logical_date` is a **`pendulum.DateTime` object**. It carries full date and time information and supports method calls like `.year`, `.month`, `.strftime()`, `.isoformat()`.

`logical_date` is itself equivalent to `data_interval_start` — both were introduced in Airflow 2.2 to replace the deprecated `execution_date`. In Airflow 3, `data_interval_start` is the preferred name for new code. `logical_date` remains as a compatibility alias.

Rule of thumb: use `{{ ds }}` when you need a plain date string, use `{{ data_interval_start }}` when you need a full datetime object or want to call methods on it.

---

## Q3: How do you use Jinja macros inside a BashOperator?

**Answer:**

Simply place the macro expression inside the `bash_command` string. `bash_command` is listed in `BashOperator.template_fields`, so Airflow will render it before the shell command executes.

```python
from airflow.operators.bash import BashOperator

BashOperator(
    task_id="daily_report",
    bash_command=(
        "python report.py "
        "--date {{ ds }} "
        "--run-id {{ dag_run.run_id }} "
        "--env {{ params.environment }}"
    ),
)
```

You can use any built-in macro, any `macros.*` function, and any `params.*` value. You can also use Jinja control structures like `{% if %}` and `{% for %}` inside the command string.

**Important:** Do not use `{{ ds }}` inside a Python `@task` function body — Jinja does not process Python strings. Inside `@task`, access the context dictionary: `context["ds"]`.

---

## Q4: What are `template_fields` and how do they control Jinja rendering?

**Answer:**

`template_fields` is a class-level tuple on every Airflow operator that lists the names of instance attributes that should be processed by the Jinja engine before the task runs.

```python
class BashOperator(BaseOperator):
    template_fields: Sequence[str] = ("bash_command", "env")
```

Only fields in this tuple are rendered. If you put `{{ ds }}` in a field that is NOT in `template_fields`, the string is passed to the operator as-is — no rendering happens, and you will see the literal text `{{ ds }}` rather than the date.

When building a custom operator, you declare your own `template_fields`:

```python
class MyOperator(BaseOperator):
    template_fields: Sequence[str] = ("query", "output_path")

    def __init__(self, query: str, output_path: str, **kwargs):
        super().__init__(**kwargs)
        self.query = query
        self.output_path = output_path
```

Both `self.query` and `self.output_path` will be Jinja-rendered before `execute()` is called.

---

## Q5: How do you add custom macros to Airflow?

**Answer:**

Custom macros are registered via Airflow's plugin system. You create a plugin file in the `plugins/` directory, define your Python functions, and list them in the `macros` attribute of an `AirflowPlugin` subclass.

```python
# plugins/my_macros_plugin.py
from airflow.plugins_manager import AirflowPlugin

def fiscal_quarter(ds: str) -> str:
    """Returns Q1, Q2, Q3, or Q4 for a given YYYY-MM-DD date."""
    from datetime import date
    d = date.fromisoformat(ds)
    return f"Q{(d.month - 1) // 3 + 1}"

def snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])

class MyMacrosPlugin(AirflowPlugin):
    name = "my_macros_plugin"
    macros = [fiscal_quarter, snake_to_camel]
```

After placing this file in `plugins/` and restarting the scheduler, both functions are available in any DAG template as `{{ macros.fiscal_quarter(ds) }}` and `{{ macros.snake_to_camel('hello_world') }}`.

---

## Q6: What is `macros.ds_add` and when would you use it?

**Answer:**

`macros.ds_add(ds, days)` is a built-in Airflow macro helper that performs date arithmetic. It takes a `YYYY-MM-DD` string and an integer number of days, and returns a new `YYYY-MM-DD` string with that many days added (or subtracted, for negative values).

```python
# Use case: process a rolling 7-day window
BashOperator(
    task_id="weekly_rollup",
    bash_command=(
        "aggregate.py "
        "--start {{ macros.ds_add(ds, -6) }} "  # 6 days ago
        "--end {{ ds }}"                          # today
    ),
)
```

If `ds` is `2025-03-15`:
- `macros.ds_add(ds, -6)` → `2025-03-09`
- `macros.ds_add(ds, 1)` → `2025-03-16`
- `macros.ds_add(ds, -30)` → `2025-02-13`

It is simpler than calling `data_interval_start.add(days=-6).to_date_string()` when you just need a plain string result.

---

## Q7: What is `dag_run.conf` and how is it different from `params`?

**Answer:**

Both carry runtime data into tasks, but they serve different purposes:

**`dag_run.conf`** is an untyped, unvalidated JSON dictionary that is attached to a specific DAG run when it is triggered manually (via UI or CLI with `--conf`). It is ephemeral — it only exists for that one run and is not part of the DAG definition.

**`params`** are typed, validated parameters defined in the DAG itself using `Param` objects. They have types (`string`, `integer`, etc.), default values, and descriptions. They are part of the DAG definition and are displayed in the trigger UI as a form.

```python
# dag_run.conf: set at trigger time, no schema
# Access: {{ dag_run.conf.get('key', 'default') }}
airflow dags trigger my_dag --conf '{"override_date": "2025-01-01"}'

# params: defined in DAG code, typed, validated
from airflow.models.param import Param
params={"batch_size": Param(100, type="integer", minimum=1, maximum=10000)}
# Access: {{ params.batch_size }}
```

In practice: use `params` for expected, well-defined inputs with validation. Use `dag_run.conf` for ad-hoc overrides or when the payload structure varies.

---

## Q8: When should you use `prev_data_interval_start_success` and what is its gotcha?

**Answer:**

Use `prev_data_interval_start_success` when building **incremental data pipelines** where you want to load only new records since the last successful run, rather than reprocessing all data every time.

```python
BashOperator(
    task_id="incremental_sync",
    bash_command=(
        "sync.py "
        "--from {{ prev_data_interval_start_success or '1970-01-01' }} "
        "--to {{ ds }}"
    ),
)
```

**The gotcha:** On the very first run of a DAG, there is no prior successful run, so `prev_data_interval_start_success` is `None`. If your template does not handle `None`, the rendered command will contain the string `None`, which will likely cause an error.

Always provide a fallback using Jinja's `or` operator:
```
{{ prev_data_interval_start_success or '1970-01-01' }}
```
Or use an `{% if %}` block for more complex handling.

---

## Q9: Can you use Jinja templates inside a `@task` decorated function?

**Answer:**

No — Jinja templates only apply to fields listed in `template_fields`. A `@task` decorated function is a Python function body, and Airflow does not process Python strings as Jinja templates.

Inside a `@task` function, you access the same runtime values through the **context dictionary**:

```python
from airflow.decorators import task

@task
def process_data(**context):
    ds = context["ds"]                              # "2025-03-15"
    start = context["data_interval_start"]          # pendulum.DateTime
    run_id = context["dag_run"].run_id              # "scheduled__2025-03-15..."
    env = context["params"]["environment"]          # "production"

    print(f"Processing {ds} in {env}")
```

The `**context` pattern makes Airflow inject all context variables automatically. Alternatively, you can use typed context injection in Airflow 3 with `get_current_context()`.

---

## Q10: What changed in Airflow 3 regarding Jinja templates and macros?

**Answer:**

Airflow 3 made several improvements to the templating system:

1. **`execution_date` is fully removed.** In Airflow 2.x it was deprecated but still present. Airflow 3 drops it completely. Use `data_interval_start` or `logical_date` instead.

2. **Improved Params UI.** When triggering a DAG manually, typed `Param` objects now render a proper form in the trigger modal — text boxes for strings, number spinners for integers, checkboxes for booleans — rather than a raw JSON text area.

3. **Better type safety.** Param validation is enforced at trigger time, so invalid values are rejected before the DAG run is created.

4. **Consistent context API.** The context dictionary keys are more consistent and the deprecation warnings from Airflow 2.x are gone.

5. **`logical_date` remains** as a compatibility alias for `data_interval_start` to ease migration from Airflow 2.x code.
