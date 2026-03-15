# PythonOperator — Cheatsheet

The most used operator in production Airflow. This card covers everything from the basic signature to the TaskFlow API comparison and XCom pitfalls.

---

## What It Does in One Sentence

Calls any Python function as an Airflow task — return value goes to XCom, any raised exception fails the task.

---

## Import

```python
from airflow.operators.python import PythonOperator
```

No provider package needed — part of Airflow core.

---

## Key Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `python_callable` | `callable` | **required** | Reference (not call) to your Python function |
| `op_kwargs` | `dict` | `None` | Keyword arguments passed to the callable |
| `op_args` | `list` | `None` | Positional arguments passed to the callable |
| `templates_dict` | `dict` | `None` | Dict of Jinja-templated values; accessible via `templates_dict` in context |
| `show_return_value_in_logs` | `bool` | `True` | Whether to log the return value |

---

## Template Fields (Jinja-aware)

`op_kwargs`, `op_args`, `templates_dict` — values inside these support `{{ ds }}`, `{{ run_id }}`, `{{ var.value.x }}`, etc.

---

## Code Patterns

### Basic Usage

```python
def greet():
    print("Hello from a task!")
    return "success"

PythonOperator(
    task_id="greet",
    python_callable=greet,
)
```

---

### With `op_kwargs`

```python
def process(source: str, date: str):
    print(f"Processing {source} for {date}")

PythonOperator(
    task_id="process",
    python_callable=process,
    op_kwargs={
        "source": "/data/input",
        "date": "{{ ds }}",    # Jinja template — rendered at runtime
    },
)
```

---

### Accessing Task Context

```python
def my_task(**context):
    ti = context["ti"]
    run_date = context["ds"]
    run_id = context["run_id"]
    print(f"Run {run_id} for {run_date}")

PythonOperator(
    task_id="contextual",
    python_callable=my_task,
)
```

Your function must accept `**context` (or `**kwargs`) to receive the context dict.

---

### Pushing and Pulling XCom

```python
# Producer — return value is automatically pushed
def extract(**context):
    return {"rows": 1542, "source": "api"}

# Consumer — pull using ti.xcom_pull
def validate(**context):
    result = context["ti"].xcom_pull(task_ids="extract")
    assert result["rows"] > 0

extract_task = PythonOperator(task_id="extract", python_callable=extract)
validate_task = PythonOperator(task_id="validate", python_callable=validate)
extract_task >> validate_task
```

---

### With `@task` Decorator (TaskFlow API — Equivalent)

```python
from airflow.decorators import task

@task
def extract():
    return {"rows": 1542}

@task
def validate(result: dict):
    assert result["rows"] > 0

# TaskFlow handles XCom and dependencies automatically
validate(extract())
```

---

### Using an Airflow Hook Inside a Callable

```python
def load(**context):
    from airflow.providers.postgres.hooks.postgres import PostgresHook
    hook = PostgresHook(postgres_conn_id="my_postgres")
    hook.run("INSERT INTO logs VALUES (%s)", parameters=(context["ds"],))

PythonOperator(task_id="load_log", python_callable=load)
```

---

## PythonOperator vs `@task` Decorator

| Feature | PythonOperator | `@task` Decorator |
|---|---|---|
| Syntax | Explicit instantiation | Decorator on function |
| XCom passing | Manual (`xcom_pull`) | Transparent (return value flows directly) |
| Dependency declaration | Explicit `>>` / `<<` | Inferred from data flow |
| `task_id` | Set explicitly | Inferred from function name |
| Boilerplate | More | Less |
| Best for | Backward compat, complex configs | New DAGs, clean data pipelines |

Both compile down to the same execution — choose based on your team's style.

---

## When to Use PythonOperator

| Use it when... | Avoid it when... |
|---|---|
| Custom Python logic | Simple shell commands (use BashOperator) |
| API calls and data parsing | Full environment isolation needed (use DockerOperator) |
| Data transformation / validation | Long-running ML training (use dedicated ML operators) |
| Business logic with conditionals | Conflicting library dependencies (use PythonVirtualenvOperator) |
| No dedicated operator exists | Large data should never flow through XCom — use storage paths instead |

---

## Common Pitfalls

1. **Calling the function instead of passing a reference** — `python_callable=my_func()` calls at parse time; use `python_callable=my_func`
2. **Pushing large objects via XCom** — DataFrames and large lists bloat the metadata DB; push file paths instead
3. **Function not importable** — function must be defined in a module the worker can import; avoid defining inside lambdas
4. **Missing `**context`** — function must accept `**context` (or `**kwargs`) to access `ti`, `ds`, `run_id`, etc.
5. **Forgetting to set `>>` when not using TaskFlow** — PythonOperator does not auto-create dependencies

---

## Golden Rules

- Pass the function *reference*, never the call — `python_callable=my_func`, not `my_func()`
- Keep your callables small and focused — one task, one responsibility
- Push file paths or metadata via XCom, never large data objects
- Accept `**context` in every callable — it gives you access to dates, run IDs, and XCom without extra setup
- When writing new pipelines, prefer `@task` decorator for cleaner DAG code — PythonOperator is for when you need the explicit interface

---

## Quick Context Keys Reference

```python
def my_task(**context):
    context["ds"]              # '2024-01-15'  execution date string
    context["execution_date"]  # pendulum datetime object
    context["run_id"]          # 'scheduled__2024-01-15T00:00:00+00:00'
    context["ti"]              # TaskInstance — use for xcom_pull/xcom_push
    context["dag_run"]         # DagRun object
    context["params"]          # DAG params dict
    context["prev_ds"]         # previous execution date string
```

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ **Cheatsheet.md** | ← you are here |
| 🎯 [Interview_QA.md](./Interview_QA.md) | Interview prep |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [01_BashOperator](../01_BashOperator/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [03_PostgresOperator](../03_PostgresOperator/Theory.md)
