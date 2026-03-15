# DAG Params and Runtime Configuration — Interview Q&A

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Code Examples](./Code_Example.md)**

---

## Q1: What are DAG Params in Airflow and what problem do they solve?

**Answer:**

DAG Params are typed, validated, named input parameters that you define on a DAG to allow runtime customization without changing code. They solve the problem of needing to run the same DAG logic with different inputs — different date ranges, different target tables, different environments — without deploying code changes.

Before Params, engineers often embedded configuration directly in DAG code or used environment variables. With Params, you define a `Param("production", type="string", enum=["dev", "staging", "production"])` once in the DAG, and the Airflow UI renders a dropdown when you trigger the DAG manually. The run proceeds with the selected value.

Params are particularly valuable for:
- Backfill operations with custom date ranges
- Running the same pipeline in different environments
- One-off data reprocessing triggered by operations teams
- A/B testing pipeline variants without code changes

---

## Q2: How do you define typed Params in Airflow 3?

**Answer:**

Params are defined using `Param` objects in the `params` dictionary of the DAG decorator or constructor:

```python
from airflow.decorators import dag
from airflow.models.param import Param
from datetime import datetime

@dag(
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    params={
        "environment": Param(
            "production",
            type="string",
            enum=["development", "staging", "production"],
            description="Deployment environment",
        ),
        "batch_size": Param(
            1000,
            type="integer",
            minimum=1,
            maximum=50000,
        ),
        "dry_run": Param(False, type="boolean"),
        "start_date": Param("2025-01-01", type="string", format="date"),
    },
)
def my_dag():
    ...
```

Available types are `"string"`, `"integer"`, `"number"`, `"boolean"`, `"array"`, and `"object"`. Validation constraints like `enum`, `minimum`, `maximum`, and `format` are enforced when the DAG is triggered — invalid values are rejected before the run is created.

---

## Q3: What is the difference between `dag_run.conf` and `params`?

**Answer:**

They serve similar but distinct purposes:

**`params`** are defined in the DAG code as `Param` objects with types, defaults, and validation. They always have a value — either the default or an override from the trigger. They render as a typed form in the Airflow 3 UI.

**`dag_run.conf`** is an untyped raw JSON dictionary attached to a specific DAG run when it is triggered manually. It has no schema, no defaults, and no UI form — it is whatever the person triggering the DAG sends.

The key relationship: when you trigger a DAG with `--conf '{"key": "value"}'`, those conf values are merged into `params` for that run, overriding the defaults. So `params` always holds the final, authoritative resolved values, while `dag_run.conf` holds only what was explicitly sent at trigger time.

```python
# If triggered with --conf '{"environment": "staging"}'
context["params"]["environment"]      # "staging"  (conf overrode default)
context["params"]["batch_size"]       # 1000       (default, not in conf)
context["dag_run"].conf               # {"environment": "staging"}  (only what was passed)
context["dag_run"].conf.get("batch_size")  # None  (not in conf)
```

Use `params` for accessing resolved values in tasks. Use `dag_run.conf` only when you need to know exactly what was explicitly passed vs. defaulted.

---

## Q4: How do you trigger a DAG with configuration from the command line?

**Answer:**

Use the `--conf` flag with the `airflow dags trigger` command, passing a JSON string:

```bash
# Basic
airflow dags trigger my_dag --conf '{"environment": "staging"}'

# Multiple params
airflow dags trigger reprocess_sales \
  --conf '{
    "start_date": "2024-01-01",
    "end_date": "2024-03-31",
    "dry_run": true,
    "batch_size": 500
  }'

# With custom run ID and logical date
airflow dags trigger reprocess_sales \
  --run-id "manual_q1_reprocess" \
  --exec-date "2024-03-31" \
  --conf '{"start_date": "2024-01-01", "end_date": "2024-03-31"}'
```

The JSON values in `--conf` are merged into the `params` for the run, overriding any defaults defined in the DAG. The same can be achieved via the REST API or the Airflow 3 UI trigger modal.

---

## Q5: How do you access Params inside a `@task` function?

**Answer:**

Inside a `@task` function, you access params through the context dictionary. Add `**context` to your function signature to receive it automatically:

```python
from airflow.decorators import task

@task
def process_data(**context):
    params = context["params"]

    environment = params["environment"]          # string
    batch_size  = params["batch_size"]           # integer
    dry_run     = params["dry_run"]              # boolean
    start_date  = params.get("start_date", "2025-01-01")  # with fallback

    if dry_run:
        print(f"[DRY RUN] Would process {start_date} in {environment}")
        return

    print(f"Processing {start_date} in {environment} with batches of {batch_size}")
```

Alternatively, use `get_current_context()` if you cannot add `**context` to the signature:

```python
from airflow.operators.python import get_current_context

def my_callable():
    context = get_current_context()
    return context["params"]["environment"]
```

Do not use `{{ params.name }}` Jinja syntax inside Python function bodies — that syntax only works in `template_fields` strings.

---

## Q6: Can you use Jinja templates as default Param values?

**Answer:**

Yes. Default values for `Param` objects support Jinja templating. This is useful for date-based params where the sensible default is "today's date" (the DAG run's `ds`):

```python
params={
    "process_date": Param(
        "{{ ds }}",
        type="string",
        format="date",
        description="Date to process. Defaults to the DAG run date.",
    ),
}
```

When the DAG runs on a schedule, `{{ ds }}` is rendered to the current run's date interval start. When triggered manually without overriding, the same default applies. When triggered with an explicit value, the provided value is used instead.

This pattern is powerful for backfill use cases: the DAG works automatically on schedule, but an operator can override the date for ad-hoc reprocessing.

---

## Q7: How does Airflow 3 improve the Params UI compared to Airflow 2?

**Answer:**

In Airflow 2.x, triggering a DAG with config showed a basic JSON textarea where you typed raw JSON. There was no validation, no type awareness, and no guidance on what fields were expected.

In Airflow 3, the trigger modal generates a **dynamic typed form** from the `Param` definitions:

| Param type | Airflow 3 UI widget |
|---|---|
| `string` | Text input box |
| `string` + `enum` | Dropdown selector |
| `string` + `format: "date"` | Date picker |
| `integer` / `number` | Number input with min/max constraints |
| `boolean` | Toggle or checkbox |
| `array` | JSON array editor |
| `object` | JSON object editor |

Each field shows the `title` and `description` from the `Param` definition as label and helper text. Validation runs in real-time — entering "abc" in an integer field shows an error before submission. This makes the DAG self-documenting and makes it safe to hand off trigger responsibilities to non-engineers.

---

## Q8: What happens to Params in a scheduled (non-manual) run?

**Answer:**

In a scheduled run, no `--conf` is passed, so `dag_run.conf` is an empty dictionary `{}`. All params use their **default values** as defined in the `Param` objects.

```python
params={
    "environment": Param("production", type="string"),  # → "production"
    "batch_size": Param(1000, type="integer"),           # → 1000
}
```

This is by design: scheduled runs should work reliably with sensible defaults. Manual runs allow overriding. The same DAG code handles both cases without any conditional logic needed in the task itself.

The one exception is when you use Jinja in default values (e.g., `Param("{{ ds }}", type="string", format="date")`). In scheduled runs, the Jinja template is rendered using the schedule's data interval, giving you the correct date automatically.
