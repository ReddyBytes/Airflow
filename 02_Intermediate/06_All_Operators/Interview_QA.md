# 04 — Operators: Interview Q&A

## Q1: What is an operator in Apache Airflow?

**Answer:**

An operator defines a single unit of work in a DAG. It is a template that encapsulates the logic to perform a specific task — running a bash command, executing a Python function, querying a database, or waiting for a file.

When you create a task in a DAG, you instantiate an operator. The operator's `execute()` method is called when the task runs.

```python
from airflow.operators.bash import BashOperator

my_task = BashOperator(
    task_id="say_hello",
    bash_command="echo 'Hello, Airflow!'",
)
```

Key point: the operator is the **what** — what action the task performs.

---

## Q2: What is the difference between an Operator and a Sensor?

**Answer:**

Both are subclasses of `BaseOperator`, but they serve different purposes:

| | Operator | Sensor |
|---|---|---|
| Purpose | Executes an action | Waits for a condition |
| Behavior | Runs once and completes | Polls repeatedly until condition is met |
| Blocking | Finishes quickly | Can block for minutes or hours |
| Example | `BashOperator` runs a command | `FileSensor` waits for a file |

A sensor keeps calling its `poke()` method on an interval until it returns `True` (or it times out). A regular operator calls `execute()` once.

---

## Q3: What is BaseOperator and why does it matter?

**Answer:**

`BaseOperator` is the parent class for all operators in Airflow. Every operator — built-in or custom — inherits from it.

It provides all the common task parameters that every task needs:
- `task_id`, `retries`, `retry_delay`
- `execution_timeout`, `depends_on_past`
- `email_on_failure`, `on_failure_callback`
- `pool`, `priority_weight`, `trigger_rule`

Because every operator inherits these, you configure retry behavior the same way whether you are using `BashOperator`, `PostgresOperator`, or a custom operator.

---

## Q4: How do you create a custom operator?

**Answer:**

Subclass `BaseOperator` and implement the `execute()` method:

```python
from airflow.models import BaseOperator

class SlackNotifyOperator(BaseOperator):

    def __init__(self, message: str, channel: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.channel = channel

    def execute(self, context):
        self.log.info(f"Sending to {self.channel}: {self.message}")
        # call Slack API here
        send_slack_message(self.channel, self.message)
```

Rules:
1. Always call `super().__init__(**kwargs)` to pass `BaseOperator` params through
2. Implement `execute(self, context)` — this is where your logic lives
3. Store parameters as instance attributes in `__init__`

---

## Q5: What are retries and retry_delay, and how do they work?

**Answer:**

`retries` sets how many times Airflow will retry a failed task before marking it as permanently failed. `retry_delay` sets the wait time between attempts.

```python
from datetime import timedelta

my_task = BashOperator(
    task_id="flaky_api_call",
    bash_command="curl https://api.example.com/data",
    retries=3,
    retry_delay=timedelta(minutes=5),
)
```

With `retries=3`, the task will be attempted up to 4 times total (1 original + 3 retries). Between each retry, Airflow waits `retry_delay`. If all retries fail, the task state becomes `failed`.

You can also use `retry_exponential_backoff=True` to increase the wait time exponentially between retries (useful for rate-limited APIs).

---

## Q6: What are the rules for naming task_id?

**Answer:**

- Must be **unique within the DAG** — no two tasks in the same DAG can share a `task_id`
- Should use **alphanumeric characters, underscores, hyphens, and dots** only
- No spaces
- Case-sensitive (`load_data` and `Load_Data` are different)
- Should be **descriptive** — `extract_sales_data` is better than `task_1`

Bad:
```python
task_id="my task"       # spaces not allowed
task_id="extract"       # too vague
task_id="extract"       # duplicate in same DAG — will raise error
```

Good:
```python
task_id="extract_sales_data_from_postgres"
task_id="transform_and_clean_records"
task_id="load_to_s3_bucket"
```

---

## Q7: What is the difference between Action, Transfer, Sensor, and Utility operators?

**Answer:**

| Type | Purpose | Example |
|---|---|---|
| **Action** | Executes a job or task | `BashOperator`, `PythonOperator` |
| **Transfer** | Moves data between systems | `LocalFilesystemToS3Operator`, `S3ToRedshiftOperator` |
| **Sensor** | Waits for a condition | `FileSensor`, `HttpSensor` |
| **Utility** | Controls DAG flow | `BranchPythonOperator`, `TriggerDagRunOperator` |

This is a logical categorization, not a strict technical one. All of them ultimately inherit from `BaseOperator`.

---

## Q8: What is the execute() method?

**Answer:**

`execute(self, context)` is the main method of every operator. When Airflow runs a task, it calls this method. The `context` argument is a dictionary containing runtime information about the current DAG run:

```python
def execute(self, context):
    dag_run_id = context["run_id"]
    execution_date = context["execution_date"]
    task_instance = context["ti"]

    # Push a value to XCom
    task_instance.xcom_push(key="result", value=42)

    return "done"
```

The return value of `execute()` is automatically pushed to XCom as the default XCom value.

---

## Q9: What is the provider package system and why does it matter for operators?

**Answer:**

Airflow's core package only includes a handful of built-in operators. Most operators for external systems (AWS, GCP, databases, APIs) live in **provider packages** — separate pip packages maintained by the community or cloud vendors.

```bash
# Install AWS provider for S3 operators
pip install apache-airflow-providers-amazon

# Install Postgres provider
pip install apache-airflow-providers-postgres

# Install Google Cloud provider
pip install apache-airflow-providers-google
```

This means you only install what you need. Providers are versioned independently from Airflow core, so they can be updated without upgrading Airflow itself.

---

## Q10: How does execution_timeout work, and why should you always set it?

**Answer:**

`execution_timeout` sets a maximum wall-clock duration for a task. If the task runs longer than this, Airflow kills it and marks it as `failed`.

```python
from datetime import timedelta

slow_task = PythonOperator(
    task_id="process_large_file",
    python_callable=process_file,
    execution_timeout=timedelta(hours=2),
)
```

**Why you should always set it:**
- A task can hang indefinitely (network issue, deadlock, infinite loop)
- A hanging task holds a worker slot, blocking other tasks
- Without a timeout, one bad task can freeze your entire pipeline

A good rule of thumb: set `execution_timeout` to 2-3x the expected normal runtime of the task.
