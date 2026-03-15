# Core Operators — Interview Q&A

## 8 Questions on BashOperator, PythonOperator, and EmptyOperator

---

**Q1. What is BashOperator and what are its most important parameters?**

`BashOperator` executes a bash command or shell script in a subprocess on the Airflow Worker. It is the simplest way to run CLI tools, shell scripts, or any command that is available in the Worker's environment.

The most important parameters:

- `bash_command` (required): The shell command to run. This is a Jinja-templated string, so you can use `{{ ds }}`, `{{ execution_date }}`, etc.
- `env`: A dictionary of environment variables to set for the subprocess.
- `append_env`: If `True`, the `env` dict is merged with the current system environment. If `False` (default), only `env` is used.
- `cwd`: Working directory for the command.
- `skip_on_exit_code`: If the command exits with this code, the task is marked as `skipped` instead of `failed`.
- `do_xcom_push`: If `True` (default), the last line of stdout is pushed to XCom.

Common use case: calling `dbt run`, `spark-submit`, `aws s3 cp`, or any shell script that already exists.

---

**Q2. How does PythonOperator pass data between tasks?**

`PythonOperator` uses **XCom** (cross-task communication) to pass data between tasks.

**Pushing data:** The return value of the Python callable is automatically pushed to XCom under the key `return_value`:

```python
def my_func():
    return 42  # pushed to XCom as 'return_value'
```

You can also push explicitly:
```python
def my_func(**context):
    context["task_instance"].xcom_push(key="my_key", value={"result": 42})
```

**Pulling data:** The downstream task pulls the value using the task instance:

```python
def downstream_func(**context):
    value = context["task_instance"].xcom_pull(task_ids="my_func")
    print(value)  # 42
```

Important limitation: XCom values are stored in the Metadata Database. They are suitable for small values (IDs, counts, file paths) but not large datasets. Never push a DataFrame or large binary blob through XCom.

---

**Q3. What is EmptyOperator used for? Give three real use cases.**

`EmptyOperator` is a task that does nothing — it executes instantly and always succeeds. Despite doing nothing, it is very useful for:

**Use case 1: Pipeline anchors**
Creating a clear `start` and `end` node makes the DAG graph easier to read. Other tasks depend on `start`, and `end` depends on the final tasks.

```python
start = EmptyOperator(task_id="start")
end   = EmptyOperator(task_id="end")
start >> [extract, validate] >> transform >> end
```

**Use case 2: Branch join points**
When a DAG has branches (parallel paths), you often need a single downstream task that runs after all branches complete. `EmptyOperator` with `trigger_rule="none_failed_min_one_success"` serves as this join node cleanly.

**Use case 3: Work-in-progress placeholder**
During development, you can sketch out a DAG with all the task names as `EmptyOperator` instances, set up the dependencies, and then replace each `EmptyOperator` with real operators one at a time.

---

**Q4. What is the difference between `op_args`, `op_kwargs`, and `templates_dict` in PythonOperator?**

All three are ways to pass values into your Python callable:

- **`op_args`** — a list of positional arguments. These are passed directly to the function as positional args. They are NOT Jinja-templated.

- **`op_kwargs`** — a dictionary of keyword arguments. These are passed to the function as keyword args. Strings in `op_kwargs` ARE Jinja-templated (e.g., `"{{ ds }}"` becomes the execution date string).

- **`templates_dict`** — a special dictionary that is also Jinja-templated. It is passed to the callable as a `templates_dict` keyword argument. Useful when you want to separate templated values from regular kwargs.

```python
def my_func(fixed_value, date_str, extra):
    print(fixed_value)        # "hello" — from op_kwargs
    print(date_str)           # "2024-01-15" — from op_kwargs with template
    print(extra["report_date"]) # "2024-01-15" — from templates_dict

PythonOperator(
    task_id="example",
    python_callable=my_func,
    op_kwargs={
        "fixed_value": "hello",
        "date_str": "{{ ds }}",  # templated
    },
    templates_dict={
        "report_date": "{{ ds }}"
    },
)
```

---

**Q5. When would you use BashOperator vs PythonOperator?**

This is a common practical question with a practical answer:

**Use BashOperator when:**
- You already have a working shell script (`./scripts/process.sh`).
- You need to call a CLI tool (`dbt run`, `spark-submit`, `aws s3 cp`, `gsutil`).
- You want to run a Python script as a separate subprocess (`python scripts/etl.py`).
- You need to chain multiple shell commands with pipes or redirects.

**Use PythonOperator when:**
- You are writing new logic in Python.
- You need Python libraries (pandas, requests, SQLAlchemy, etc.).
- You need to interact with XCom directly.
- You need testable, type-annotated business logic.
- You want to access the Airflow context (execution date, dag run ID, etc.) in your code.

In practice, PythonOperator is more flexible and testable. BashOperator is better when you want to reuse existing shell scripts or CLI tools without wrapping them in Python.

---

**Q6. What happens if a BashOperator's command returns a non-zero exit code?**

By default, any non-zero exit code causes the task to fail. Airflow monitors the subprocess exit code and marks the task as `failed` if it is non-zero.

The exception is `skip_on_exit_code`: if you set this parameter, the specified exit code causes a `skipped` state instead:

```python
BashOperator(
    task_id="optional_task",
    bash_command="check_condition.sh",
    skip_on_exit_code=99,
    # Exit 0 → success
    # Exit 99 → skipped
    # Any other exit code → failed
)
```

This is useful for tasks that are conditionally run — the bash script decides whether to run or skip based on business logic.

---

**Q7. What is the `@task` decorator in Airflow 3 and how does it relate to PythonOperator?**

The `@task` decorator is syntactic sugar for `PythonOperator`. It is part of the **TaskFlow API** introduced in Airflow 2.0 and recommended for new code in Airflow 3. Under the hood, it creates a `PythonOperator` task.

**Benefits of `@task` over `PythonOperator`:**
- Cleaner, more Pythonic syntax.
- Return values of one `@task` function can be passed directly to another as arguments — Airflow handles the XCom push/pull automatically.
- Type annotations work naturally.

```python
from airflow.sdk import DAG, task
from datetime import datetime

with DAG("taskflow_example", start_date=datetime(2024, 1, 1), schedule="@daily") as dag:

    @task
    def extract() -> list[dict]:
        return [{"id": 1, "value": 100}]

    @task
    def transform(records: list[dict]) -> int:
        return sum(r["value"] for r in records)

    @task
    def load(total: int) -> None:
        print(f"Loading total: {total}")

    # The return value of extract() is passed directly to transform()
    # Airflow handles XCom automatically
    load(transform(extract()))
```

You can mix `@task` decorated functions and `PythonOperator` instances in the same DAG.

---

**Q8. How do you handle errors in PythonOperator tasks? What happens when a Python function raises an exception?**

When the Python callable raises any uncaught exception, Airflow catches it, marks the task as `failed`, and writes the full traceback to the task's log.

**Retry behavior:** If the task has retries configured, Airflow marks it as `up_for_retry` and re-runs it after the retry delay. The function is called again from scratch.

```python
from airflow.operators.python import PythonOperator
from airflow.exceptions import AirflowSkipException, AirflowFailException

def my_func():
    # Raise to fail with a clear message
    raise AirflowFailException("Something went wrong!")

    # Raise to skip this task (not fail)
    raise AirflowSkipException("Condition not met, skipping.")

PythonOperator(
    task_id="my_task",
    python_callable=my_func,
    retries=3,
    retry_delay=timedelta(minutes=5),
)
```

**Best practices:**
- Use `AirflowSkipException` (not a regular exception) to intentionally skip a task.
- Use `AirflowFailException` to fail a task immediately without retrying.
- Let regular exceptions propagate naturally — Airflow will catch them, log the traceback, and apply retry logic.
- Always log what went wrong before raising, so the logs are useful for debugging.
