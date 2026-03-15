# 08 — Variables and Config: Interview Q&A

---

**Q1. What are Airflow Variables?**

Airflow Variables are key-value pairs stored in the metadata database. They allow you to centralise configuration values — such as bucket names, API endpoints, and thresholds — so that DAG code never contains hardcoded environment-specific strings. When a value changes, you update it once and every DAG reads the new value on its next run.

---

**Q2. How do you set an Airflow Variable?**

Three ways:
1. **UI** — Admin → Variables → add a record.
2. **CLI** — `airflow variables set <key> <value>`.
3. **Environment variable** — `export AIRFLOW_VAR_<KEY_UPPERCASE>=<value>`.

You can also call `Variable.set("key", "value")` programmatically in Python, and import a batch of variables from a JSON file with `airflow variables import`.

---

**Q3. How do you use a Variable inside a DAG?**

Call `Variable.get("key")` inside a task callable (not at module level):

```python
from airflow.models import Variable

def my_task():
    bucket = Variable.get("s3_bucket", default_var="fallback-bucket")
    ...
```

For JSON variables add `deserialize_json=True`:

```python
config = Variable.get("pipeline_config", deserialize_json=True)
env = config["env"]
```

---

**Q4. What is the difference between an Airflow Variable and a Connection?**

| | Variable | Connection |
|---|---|---|
| Purpose | Config values (names, flags, thresholds) | Credentials to external systems |
| Stored as | Key-value string | Structured record (host, port, login, password, extra) |
| Accessed via | `Variable.get()` | Hook / Operator `conn_id` parameter |
| Use for secrets? | Not recommended | Yes (encrypt password field) |

---

**Q5. How do you pass a Variable's value to a task without calling Variable.get() in Python?**

Use **Jinja templating** in the operator's templated fields:

```python
BashOperator(
    task_id="upload",
    bash_command="aws s3 cp /tmp/out.csv s3://{{ var.value.s3_bucket }}/out.csv",
)
```

The template is rendered at task execution time, so no Python code is needed.

---

**Q6. What happens if you call Variable.get() at module level?**

It runs every time the scheduler parses the DAG file — potentially many times per minute. This hammers the metadata database with unnecessary queries and can cause performance problems. Always call `Variable.get()` inside a function that is only executed when the task runs.

---

**Q7. What is the AIRFLOW_VAR_* environment variable format?**

```
AIRFLOW_VAR_<KEY_UPPERCASE>=<value>
```

Example: `AIRFLOW_VAR_S3_BUCKET=my-bucket` is read by `Variable.get("s3_bucket")`. Environment variable values take precedence over anything stored in the metadata DB. This is useful for containers and secrets that should not be persisted in the database.

---

**Q8. How do you store and retrieve a dictionary as a Variable?**

Store it as a JSON string and use `deserialize_json=True`:

```python
# Store
Variable.set("config", {"env": "prod", "retries": 3}, serialize_json=True)

# Retrieve
config = Variable.get("config", deserialize_json=True)
print(config["retries"])  # 3
```

---

**Q9. What is Jinja templating in Airflow and how does it relate to Variables?**

Jinja is a Python template engine that Airflow uses to render dynamic values into operator parameters at task execution time. Airflow exposes Variables in the Jinja context via `var.value.<key>` (plain string) and `var.json.<key>` (JSON variable). Only fields listed in an operator's `template_fields` attribute support Jinja.

---

**Q10. Should you store passwords in Airflow Variables?**

No. Variables are stored as plain text in the metadata database (even though the UI masks them by default if the key contains "password" or "secret"). For credentials, use **Connections** (the password field is encrypted) or a **secrets backend** such as Vault or AWS Secrets Manager.
