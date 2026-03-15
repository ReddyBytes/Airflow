# PythonOperator — Interview Q&A

The most widely used operator in production Airflow. You need to understand not just how to use it, but *when* it is the right choice, how data flows through it, and how it compares to the TaskFlow API.

---

## Beginner Questions

**Q1. What is PythonOperator and what does it do?**

PythonOperator lets you run any Python function as an Airflow task. You define a regular Python function with your logic, hand a reference to it over to `PythonOperator`, and Airflow calls it when the task runs.

```python
from airflow.operators.python import PythonOperator

def say_hello():
    print("Hello from Airflow!")

hello_task = PythonOperator(
    task_id="say_hello",
    python_callable=say_hello,
)
```

It is the "do anything" operator — if no dedicated operator exists for your use case, PythonOperator almost certainly can handle it.

---

**Q2. What is the `python_callable` parameter?**

`python_callable` is the only required parameter (besides `task_id`). It accepts a **reference** to a Python function — not a function call. You pass the name without parentheses:

```python
# Correct — pass the reference
PythonOperator(python_callable=my_function)

# Wrong — this calls the function immediately at DAG parse time
PythonOperator(python_callable=my_function())
```

The function must be importable by the Airflow worker — defined in the DAG file or in a module on the Python path.

---

**Q3. What is `op_kwargs` and how do you use it?**

`op_kwargs` is a dictionary of keyword arguments that Airflow passes to your function when it calls it. It is the cleanest way to parameterize your callable:

```python
def load_data(source_path: str, date: str):
    print(f"Loading from {source_path} for {date}")

load_task = PythonOperator(
    task_id="load",
    python_callable=load_data,
    op_kwargs={
        "source_path": "/data/input",
        "date": "{{ ds }}",   # Jinja template — rendered at runtime
    },
)
```

Jinja templates inside `op_kwargs` values are rendered before being passed to your function.

---

**Q4. Where is PythonOperator imported from in Airflow 3?**

```python
from airflow.operators.python import PythonOperator
```

Part of Airflow core — no provider package required.

---

**Q5. What happens if your Python function raises an exception?**

If the callable raises any exception, the task fails. Airflow captures the traceback and shows it in the task log. The task is marked as `failed` and will retry if `retries` is set. Return `None` (or any value) to succeed; raise any exception to fail.

---

## Intermediate Questions

**Q6. How do you pass data between tasks using PythonOperator?**

Via XCom. Any value your function returns is automatically pushed to XCom under the key `return_value`. Downstream tasks pull it using the `TaskInstance`:

```python
def extract(**context):
    records = fetch_from_api()
    return len(records)   # pushed to XCom automatically

def validate(**context):
    count = context["ti"].xcom_pull(task_ids="extract")
    assert count > 0, f"Expected records, got {count}"

extract_task = PythonOperator(task_id="extract", python_callable=extract)
validate_task = PythonOperator(task_id="validate", python_callable=validate)
extract_task >> validate_task
```

---

**Q7. What is the `context` dictionary? What are the most important keys?**

The context dictionary is automatically injected as keyword arguments when your function accepts `**context`. It contains metadata about the current DAG run:

| Key | What it holds |
|---|---|
| `ti` / `task_instance` | TaskInstance object — use for XCom push/pull |
| `ds` | Execution date as `YYYY-MM-DD` string |
| `execution_date` | Execution date as a pendulum datetime object |
| `run_id` | Unique string ID for this DAG run |
| `dag_run` | The DagRun object |
| `dag` | The DAG object |
| `task` | The current Task object |
| `prev_ds` / `next_ds` | Previous / next scheduled execution date |
| `params` | DAG-level params dictionary |

```python
def my_task(**context):
    ti = context["ti"]
    run_date = context["ds"]
    run_id = context["run_id"]
```

---

**Q8. What is the difference between PythonOperator and the `@task` decorator?**

They achieve the same result but with different syntax. `@task` (TaskFlow API) is shorthand that removes boilerplate:

```python
# Traditional PythonOperator
def extract():
    return {"rows": 42}

extract_task = PythonOperator(
    task_id="extract",
    python_callable=extract,
)

# Equivalent with @task decorator (TaskFlow API)
@task
def extract():
    return {"rows": 42}

extract_task = extract()
```

With `@task`:
- The task_id is inferred from the function name
- XCom is handled transparently — you pass return values directly between functions
- Dependencies are implicit from the data flow
- Less code, easier to read

PythonOperator is still valid and sometimes preferred for backward compatibility, complex parameterization, or when mixing with non-TaskFlow code.

---

**Q9. What is `templates_dict` and when do you use it?**

`templates_dict` is a dictionary where Jinja templates are rendered and passed to your function under the `templates_dict` key in the context. It is an alternative to `op_kwargs` for templated values:

```python
def process(templates_dict=None, **context):
    date = templates_dict["run_date"]
    print(f"Running for {date}")

PythonOperator(
    task_id="process",
    python_callable=process,
    templates_dict={"run_date": "{{ ds }}"},
)
```

In practice, most teams put Jinja templates directly in `op_kwargs` instead — `templates_dict` is older style but still valid.

---

**Q10. What is the difference between `op_args` and `op_kwargs`?**

Both pass arguments to your callable. `op_args` passes them positionally; `op_kwargs` passes them as named keyword arguments:

```python
def greet(name, greeting):
    print(f"{greeting}, {name}!")

# op_args — positional, order must match function signature
PythonOperator(
    task_id="greet_args",
    python_callable=greet,
    op_args=["Alice", "Hello"],
)

# op_kwargs — named, order doesn't matter
PythonOperator(
    task_id="greet_kwargs",
    python_callable=greet,
    op_kwargs={"greeting": "Hello", "name": "Alice"},
)
```

Prefer `op_kwargs` — it is more readable and less fragile if you ever refactor the function signature.

---

## Advanced Questions

**Q11. When does PythonOperator NOT push to XCom automatically?**

PythonOperator pushes the return value to XCom by default. But there are cases where you might not want this:

1. **Returning `None`** — XCom is still pushed, with value `None`
2. **`show_return_value_in_logs=False`** — suppresses the return value from logs but still pushes to XCom
3. **Very large return values** — XCom is stored in the Airflow metadata database; pushing large objects (DataFrames, lists of millions of rows) will bloat it. In this case, write the data to S3/GCS/disk and push only the path

```python
def extract(**context):
    df = load_big_dataset()
    path = f"/data/output_{context['ds']}.parquet"
    df.to_parquet(path)
    return path  # push only the path, not the data
```

---

**Q12. What is the TaskFlow API and how does it compare to PythonOperator?**

The TaskFlow API (introduced in Airflow 2.0) uses the `@task` decorator to wrap Python functions as tasks. Under the hood, it still uses `PythonOperator` (or `PythonVirtualenvOperator` etc.) — it is syntactic sugar.

Advantages of TaskFlow API:
- XCom passing is transparent — returned values flow directly to the next function call
- Dependencies are inferred from data flow — no explicit `>>` needed when passing return values
- Less boilerplate — no explicit `PythonOperator(...)` instantiation

When to stick with PythonOperator:
- When you need to set parameters like `retries`, `pool`, `priority_weight` explicitly at the task level
- When mixing TaskFlow and non-TaskFlow operators in a complex dependency graph
- When working in codebases that haven't adopted TaskFlow yet

---

**Q13. Does PythonOperator run your function in memory isolation from other tasks?**

Not by default. All tasks on the same worker process share memory if they run sequentially. There is no isolation between tasks like you would get with `DockerOperator` or `KubernetesPodOperator`.

Practical implications:
- Library version conflicts between tasks on the same worker are possible
- Memory-heavy tasks can interfere with each other
- Use `PythonVirtualenvOperator` or `ExternalPythonOperator` when you need dependency isolation
- Use `DockerOperator` for full process/image isolation

---

**Q14. What happens to XCom when PythonOperator returns a large object like a pandas DataFrame?**

It is stored in the Airflow metadata database (typically PostgreSQL or MySQL). Large objects cause:
- Slow XCom serialization/deserialization
- Metadata DB bloat
- Potential failures if the object exceeds the database column size limit

Best practice: never push large datasets through XCom. Push only file paths, S3 keys, row counts, or other small metadata. Let the actual data live in your storage layer.

---

**Q15. How do you use PythonOperator when your function needs access to an Airflow connection?**

Use a Hook inside your function. Hooks are the Airflow abstraction for accessing connection credentials:

```python
def load_to_postgres(**context):
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    hook = PostgresHook(postgres_conn_id="my_postgres")
    conn = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO logs VALUES (%s)", (context["ds"],))
    conn.commit()

PythonOperator(
    task_id="load_log",
    python_callable=load_to_postgres,
)
```

This is a common pattern when PostgresOperator is not flexible enough (e.g., you need to return query results or do conditional logic based on the data).

---

## 📂 Navigation

**In this folder:**

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Concept explanation |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |
| 💻 [Code_Example.md](./Code_Example.md) | Working code |

⬅️ **Prev:** [01_BashOperator](../01_BashOperator/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [03_PostgresOperator](../03_PostgresOperator/Theory.md)
