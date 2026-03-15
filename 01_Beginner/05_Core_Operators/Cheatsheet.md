# Core Operators — Cheatsheet

## BashOperator

```python
from airflow.operators.bash import BashOperator

# Minimal
task = BashOperator(
    task_id="my_task",
    bash_command="echo hello",
)

# Full options
task = BashOperator(
    task_id="my_task",
    bash_command="echo $MY_VAR && date",
    env={"MY_VAR": "value"},        # Environment variables
    append_env=True,                  # Merge with system env
    cwd="/tmp",                       # Working directory
    output_encoding="utf-8",          # Output encoding
    skip_on_exit_code=99,             # Exit code → SKIP
    do_xcom_push=True,                # Push last stdout line to XCom
)
```

**Key facts:**
- `bash_command` is Jinja-templated: use `{{ ds }}`, `{{ execution_date }}`, etc.
- Return value (XCom): last line of stdout (when `do_xcom_push=True`).
- Script file: `bash_command="scripts/run.sh "` — trailing space required.
- Subprocess inherits Worker's environment unless `append_env=False`.

---

## PythonOperator

```python
from airflow.operators.python import PythonOperator

def my_function(param1, param2, **context):
    print(f"Execution date: {context['ds']}")
    return "result_value"   # Pushed to XCom as 'return_value'

# Minimal
task = PythonOperator(
    task_id="my_task",
    python_callable=my_function,
)

# With arguments
task = PythonOperator(
    task_id="my_task",
    python_callable=my_function,
    op_kwargs={"param1": "hello", "param2": 42},
    op_args=["positional_arg"],            # Positional args
    templates_dict={"date": "{{ ds }}"},   # Jinja-templated kwargs
    do_xcom_push=True,
)
```

**Key facts:**
- Return value: automatically pushed to XCom as `return_value`.
- Context access: add `**context` to function signature for free access to `ds`, `task_instance`, `dag`, etc.
- Pull XCom: `context["task_instance"].xcom_pull(task_ids="upstream_task")`.
- Alternative syntax: `@task` decorator (Airflow 3 preferred for new code).

### @task Decorator (Airflow 3 preferred)

```python
from airflow.sdk import DAG, task
from datetime import datetime

with DAG("my_dag", start_date=datetime(2024, 1, 1), schedule="@daily") as dag:

    @task
    def extract() -> list:
        return [1, 2, 3]

    @task
    def transform(data: list) -> int:
        return sum(data)

    # TaskFlow: return values automatically become XCom
    result = transform(extract())
```

---

## EmptyOperator

```python
from airflow.operators.empty import EmptyOperator

# Minimal — does nothing, marks as success
start = EmptyOperator(task_id="start")
end   = EmptyOperator(task_id="end")

# With trigger rule (join after parallel branches)
join = EmptyOperator(
    task_id="join",
    trigger_rule="none_failed_min_one_success",
)
```

**Key facts:**
- Executes instantly, always succeeds (unless trigger rule not met).
- No return value, no XCom push.
- Use for: pipeline anchors, branch join points, TODO placeholders.

---

## Common Trigger Rules

| Rule | Meaning |
|---|---|
| `all_success` (default) | Run only if all upstream tasks succeeded |
| `all_failed` | Run only if all upstream tasks failed |
| `all_done` | Run when all upstream tasks are done (any state) |
| `one_success` | Run as soon as any one upstream task succeeds |
| `one_failed` | Run as soon as any one upstream task fails |
| `none_failed` | Run if no upstream tasks failed (skipped is OK) |
| `none_failed_min_one_success` | Run if at least one succeeded and none failed |

---

## XCom Quick Reference

```python
# Push a value
def push_func(**context):
    context["task_instance"].xcom_push(key="my_key", value=42)
    return "auto_pushed"   # Also pushes to key='return_value'

# Pull a value
def pull_func(**context):
    ti = context["task_instance"]

    # Pull by task_id (gets 'return_value')
    val = ti.xcom_pull(task_ids="push_task")

    # Pull with specific key
    val = ti.xcom_pull(task_ids="push_task", key="my_key")
```

---

## Dependency Syntax

```python
# Single dependency
task_a >> task_b              # a before b

# Chain
task_a >> task_b >> task_c   # a → b → c

# Fan-out (parallel)
start >> [task_b, task_c]    # start → b AND c (in parallel)

# Fan-in (join)
[task_b, task_c] >> end      # both b and c → end

# Multiple chains
task_a >> task_b
task_a >> task_c
task_b >> task_d
task_c >> task_d

# List form
chain(task_a, task_b, task_c)  # from airflow.models.baseoperator import chain
```

---

## Import Paths (Airflow 3)

```python
from airflow.sdk import DAG                      # DAG class
from airflow.sdk import task                     # @task decorator
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
```
