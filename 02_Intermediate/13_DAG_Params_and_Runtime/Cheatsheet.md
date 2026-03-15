# DAG Params and Runtime Configuration — Cheatsheet

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Interview Q&A](./Interview_QA.md)**

---

## Param Types Quick Reference

| Airflow `type` | JSON Schema | Python Type | UI Widget | Validation |
|---|---|---|---|---|
| `"string"` | `string` | `str` | Text input | Length, pattern, enum |
| `"integer"` | `integer` | `int` | Number input | min, max, multipleOf |
| `"number"` | `number` | `float` | Number input | min, max |
| `"boolean"` | `boolean` | `bool` | Toggle/checkbox | — |
| `"array"` | `array` | `list` | JSON array input | minItems, maxItems |
| `"object"` | `object` | `dict` | JSON object input | required keys |
| `["string", "null"]` | multi-type | `str \| None` | Text input (optional) | Allows None/null |

---

## Param Definition Syntax

```python
from airflow.models.param import Param

# Minimal (type only)
"env": Param("production", type="string")

# With validation
"workers": Param(4, type="integer", minimum=1, maximum=64)

# With enum (dropdown in UI)
"region": Param("us-east-1", type="string",
                enum=["us-east-1", "eu-west-1", "ap-southeast-1"])

# With date format
"run_date": Param("2025-01-01", type="string", format="date")

# Optional (nullable)
"limit": Param(None, type=["integer", "null"])

# With description and title (shown in trigger UI)
"table": Param(
    "orders",
    type="string",
    title="Source Table",
    description="The BigQuery table to process",
    examples=["orders", "customers"],
)

# Boolean flag
"dry_run": Param(False, type="boolean")

# Array of strings
"tables": Param(["orders", "returns"], type="array")
```

---

## Access Patterns

```python
# In template_fields (Jinja)
bash_command = "script.py --env {{ params.environment }} --limit {{ params.limit }}"

# In @task via context
@task
def my_task(**context):
    env  = context["params"]["environment"]
    limit = context["params"].get("limit", 1000)

# In callable via get_current_context
from airflow.operators.python import get_current_context
def my_callable():
    ctx = get_current_context()
    return ctx["params"]["environment"]

# Conditional Jinja block
bash_command = (
    "script.py "
    "{% if params.dry_run %}--dry-run{% endif %} "
    "--env {{ params.environment }}"
)
```

---

## Triggering with Config

### CLI

```bash
# Basic
airflow dags trigger my_dag --conf '{"key": "value"}'

# Full example
airflow dags trigger reprocess_etl \
  --conf '{
    "start_date": "2024-01-01",
    "end_date":   "2024-03-31",
    "environment": "staging",
    "dry_run": true,
    "batch_size": 500
  }'

# Specify run ID
airflow dags trigger my_dag \
  --run-id "manual_reprocess_q1_2024" \
  --conf '{"quarter": "Q1"}'
```

### REST API

```bash
curl -X POST "http://localhost:8080/api/v1/dags/my_dag/dagRuns" \
  -H "Content-Type: application/json" \
  -u "admin:password" \
  -d '{"conf": {"environment": "staging", "batch_size": 200}}'
```

---

## UI Trigger Steps (Airflow 3)

1. Navigate to **DAGs** list
2. Click the **Trigger DAG** button (play icon) next to your DAG
3. The trigger modal opens with a **typed form** for each `Param`
4. Fill in values (Airflow 3 shows type-appropriate widgets)
5. Optionally set a **Run ID** and **Logical Date**
6. Click **Trigger**

---

## `params` vs `dag_run.conf` Side-by-Side

```python
# Params: defined in DAG, typed, validated, has defaults
params={
    "env": Param("production", type="string", enum=["dev", "prod"])
}

# Access params (always has a value — default or overridden)
context["params"]["env"]           # Python
{{ params.env }}                   # Jinja

# dag_run.conf: only set for manual triggers, untyped, no defaults
context["dag_run"].conf            # Python dict (may be {})
{{ dag_run.conf.get("env", "production") }}   # Jinja with fallback

# Relationship: conf values are merged INTO params for the run
# So params is always the complete, authoritative source
```

---

## Common Patterns

```python
# Pattern 1: Override the processing date
"process_date": Param("{{ ds }}", type="string", format="date")
# Scheduled: uses ds automatically. Manual: operator fills in a date.

# Pattern 2: Boolean feature flag
"send_alerts": Param(True, type="boolean")
# In Jinja: {% if params.send_alerts %}send_alert.sh{% endif %}

# Pattern 3: Optional row limit for testing
"limit": Param(None, type=["integer", "null"])
# In Jinja: {% if params.limit %}--limit {{ params.limit }}{% endif %}

# Pattern 4: Multi-table processing
"tables": Param(["orders", "returns"], type="array")
# In Python: for table in context["params"]["tables"]: ...

# Pattern 5: Environment-based config
"config": Param({"timeout": 30}, type="object")
# In Python: timeout = context["params"]["config"]["timeout"]
```
