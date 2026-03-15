# 18 — Callbacks and SLAs: Cheatsheet

## All Callback Types

| Callback | When it fires | Scope |
|---|---|---|
| `on_failure_callback` | Task enters FAILED state | Task or DAG level |
| `on_success_callback` | Task completes successfully | Task or DAG level |
| `on_retry_callback` | Task is about to be retried | Task or DAG level |
| `on_skipped_callback` | Task is skipped | Task or DAG level |
| `sla_miss_callback` | Task misses its SLA deadline | DAG level only |

---

## Callback Signatures

```python
# All task callbacks share the same signature
def my_callback(context: dict) -> None:
    ...

# SLA miss has a different, unique signature
def sla_miss_handler(
    dag,               # DAG object
    task_list,         # str: comma-separated task IDs that missed SLA
    blocking_task_list,# str: tasks blocking the SLA tasks
    slas,              # list[SlaMiss]: SLA miss records
    blocking_tis,      # list[TaskInstance]: blocking task instances
) -> None:
    ...
```

---

## context Dict Contents

| Key | Type | Value |
|---|---|---|
| `task_instance` (or `ti`) | `TaskInstance` | The task instance object |
| `task_instance.task_id` | `str` | Task ID |
| `task_instance.dag_id` | `str` | DAG ID |
| `task_instance.run_id` | `str` | Run ID |
| `task_instance.try_number` | `int` | Attempt number (1-based) |
| `dag_run` | `DagRun` | The DAG run object |
| `logical_date` | `datetime` | Scheduled execution time |
| `exception` | `Exception` or `None` | The exception that caused failure |
| `dag` | `DAG` | The DAG object |
| `conf` | `dict` | DAG run configuration |
| `params` | `dict` | DAG parameters |

---

## Setting Callbacks

### Task level
```python
task = PythonOperator(
    task_id="my_task",
    python_callable=my_callable,
    on_failure_callback=my_failure_handler,
    on_success_callback=my_success_handler,
    on_retry_callback=my_retry_handler,
)
```

### DAG level (applies to all tasks)
```python
with DAG(
    dag_id="my_dag",
    on_failure_callback=my_failure_handler,
    on_success_callback=my_success_handler,
    sla_miss_callback=my_sla_handler,
    ...
) as dag:
    ...
```

---

## SLA Configuration

```python
from datetime import timedelta

# SLA on a task: must finish within 2h of logical_date
task = PythonOperator(
    task_id="slow_transform",
    python_callable=transform,
    sla=timedelta(hours=2),
)

# SLA miss handler — DAG level only
def sla_miss_handler(dag, task_list, blocking_task_list, slas, blocking_tis):
    print(f"SLA missed in {dag.dag_id}: {task_list}")

with DAG(
    dag_id="my_dag",
    sla_miss_callback=sla_miss_handler,
    ...
) as dag:
    ...
```

**SLA vs execution_timeout:**

| | SLA | execution_timeout |
|---|---|---|
| What it does | Sends alert if task takes too long | **Kills** the task if it takes too long |
| Task keeps running? | Yes | No — task is marked FAILED |
| Set on | Task or DAG (sla_miss on DAG) | Task only |
| Measured from | DAG's logical_date | Task start time |

---

## Slack Notification Template

```python
def slack_failure_alert(context):
    from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook
    ti = context["task_instance"]
    message = (
        f":red_circle: *Task Failed*\n"
        f"*DAG:*  `{ti.dag_id}`\n"
        f"*Task:* `{ti.task_id}`\n"
        f"*Run:*  `{ti.run_id}`\n"
        f"*When:* `{context['logical_date']}`\n"
        f"*Error:* ```{str(context.get('exception', ''))[:400]}```"
    )
    SlackWebhookHook(slack_webhook_conn_id="slack_alerts").send(text=message)
```

## Email Notification Template

```python
def email_failure_alert(context):
    from airflow.utils.email import send_email
    ti = context["task_instance"]
    send_email(
        to=["ops@example.com"],
        subject=f"[Airflow FAILED] {ti.dag_id}.{ti.task_id}",
        html_content=f"<b>Task:</b> {ti.task_id}<br><b>Error:</b> {context.get('exception')}",
    )
```

---

## Navigation

**Prev:** [17 — Deferrable Operators](../17_Deferrable_Operators/Cheatsheet.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [19 — Pools and Resources](../19_Pools_and_Resources/Cheatsheet.md)
