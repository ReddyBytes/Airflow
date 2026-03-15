# 08 — Variables and Config: Cheatsheet

## Variable Methods

| Method | Returns | Notes |
|---|---|---|
| `Variable.get("key")` | `str` | Raises `KeyError` if not found |
| `Variable.get("key", default_var="x")` | `str` | Returns `"x"` if key missing |
| `Variable.get("key", deserialize_json=True)` | `dict / list` | Parses value as JSON |
| `Variable.set("key", "value")` | `None` | Creates or updates |
| `Variable.set("key", {"a": 1}, serialize_json=True)` | `None` | Serialises dict to JSON |
| `Variable.delete("key")` | `None` | Removes the variable |

---

## CLI Commands

```bash
# Create / update
airflow variables set <key> <value>

# Read
airflow variables get <key>

# List all keys
airflow variables list

# Delete
airflow variables delete <key>

# Export all to JSON file
airflow variables export /path/to/backup.json

# Import from JSON file
airflow variables import /path/to/backup.json
```

---

## Environment Variable Format

```bash
# Key is uppercased automatically
export AIRFLOW_VAR_<KEY_UPPERCASE>=<value>

# Examples
export AIRFLOW_VAR_S3_BUCKET=my-data-bucket
export AIRFLOW_VAR_MAX_ROWS=1000
export AIRFLOW_VAR_PIPELINE_CONFIG='{"env":"prod","retries":3}'
```

Env vars take precedence over the metadata DB. The key in your DAG is lowercase: `Variable.get("s3_bucket")` reads `AIRFLOW_VAR_S3_BUCKET`.

---

## Jinja Template Syntax

| Template | When to use |
|---|---|
| `{{ var.value.my_key }}` | Simple string variable in a templated field |
| `{{ var.json.my_key.nested }}` | JSON variable, access nested key |
| `{{ var.value.get("my_key", "default") }}` | With a fallback default |

Templated fields in operators: `bash_command`, `sql`, `email_content`, and others marked with `template_fields` in the operator class.

```python
# Example — BashOperator with variable injection
BashOperator(
    task_id="upload",
    bash_command="aws s3 cp /tmp/out.csv s3://{{ var.value.s3_bucket }}/out.csv",
)

# Example — accessing a nested JSON variable
BashOperator(
    task_id="log_env",
    bash_command="echo Running in {{ var.json.pipeline_config.env }}",
)
```

---

## Best Practices

- Call `Variable.get()` **inside task callables**, never at module level.
- Use `default_var` so missing variables degrade gracefully.
- Group related config in a **JSON variable** rather than many separate keys.
- **Prefix keys** by team or DAG to prevent name collisions (`etl_bucket`, `ml_batch_size`).
- Use **Connections** for credentials; use **Variables** for non-secret config.
- Use a **secrets backend** if variable values are sensitive.
- Store a `variables.json` in your repo (with non-secret values) so the environment can be reproduced.
