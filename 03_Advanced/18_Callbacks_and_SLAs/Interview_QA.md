# 18 — Callbacks and SLAs: Interview Q&A

---

**Q1. What are callbacks in Airflow and what are the different types?**

Callbacks are Python functions that Airflow automatically calls when specific task lifecycle events occur. There are four task-level callbacks: `on_failure_callback` (task fails), `on_success_callback` (task succeeds), `on_retry_callback` (task is about to retry), and `on_skipped_callback` (task is skipped). There is also `sla_miss_callback`, which is set at the DAG level and fires when a task exceeds its SLA time budget. All task callbacks receive a `context` dictionary. The SLA miss callback has a different, unique signature.

---

**Q2. What is the difference between task-level and DAG-level callbacks?**

A task-level callback is set on a specific operator and fires only for that task. A DAG-level callback is set on the DAG object and fires for every task in the DAG that triggers the event. For example, setting `on_failure_callback` at the DAG level means you get a notification whenever any task in the DAG fails — you don't have to add the callback to every operator individually. When both are set, both fire — task-level first, then DAG-level.

---

**Q3. What is in the context dict passed to callbacks?**

The `context` dict contains the task instance (`task_instance` or `ti`), the DAG run (`dag_run`), the logical date (`logical_date`), the exception that caused failure (`exception`, if applicable), the DAG object (`dag`), run configuration (`conf`), and DAG parameters (`params`). The task instance gives you the `task_id`, `dag_id`, `run_id`, and `try_number`. The `exception` key is particularly useful in failure callbacks to include the error message in notifications.

---

**Q4. What is an SLA in Airflow and how is it different from execution_timeout?**

An SLA (Service Level Agreement) is a maximum time budget for a task, measured from the DAG's logical date. If the task doesn't finish within `logical_date + sla`, it's an SLA miss — Airflow calls the `sla_miss_callback`. The task continues running; the SLA miss is just a notification. `execution_timeout`, on the other hand, is a hard limit measured from task start time — if the task exceeds it, Airflow kills the task and marks it `FAILED`. SLA = alerting. execution_timeout = enforcement.

---

**Q5. What is the signature of on_sla_miss and how is it different from other callbacks?**

`on_sla_miss` has a unique signature that other callbacks don't share:

```python
def sla_miss_handler(dag, task_list, blocking_task_list, slas, blocking_tis):
    ...
```

- `dag` — the DAG object
- `task_list` — a string of comma-separated task IDs that missed their SLA
- `blocking_task_list` — tasks preventing the SLA tasks from completing
- `slas` — a list of `SlaMiss` objects with details about each miss
- `blocking_tis` — list of `TaskInstance` objects that are blocking

It's also set only at the DAG level (`sla_miss_callback=...`), not on individual tasks.

---

**Q6. How would you set up a Slack notification when any task in a DAG fails?**

Set `on_failure_callback` at the DAG level with a function that uses the Slack provider:

```python
def slack_failure_alert(context):
    from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook
    ti = context["task_instance"]
    message = f":red_circle: {ti.dag_id}.{ti.task_id} FAILED on {context['logical_date']}"
    SlackWebhookHook(slack_webhook_conn_id="slack_alerts").send(text=message)

with DAG(dag_id="my_dag", on_failure_callback=slack_failure_alert, ...) as dag:
    ...
```

This fires for every task failure in the DAG without touching individual operators.

---

**Q7. How does on_retry_callback help in production?**

`on_retry_callback` fires before each retry attempt. This lets you alert teams that a task is flapping — encountering repeated failures before eventual success or final failure. A useful pattern is to only alert on retries if the attempt number is high (e.g., the third retry), indicating a persistent problem rather than a transient one:

```python
def on_retry(context):
    ti = context["task_instance"]
    if ti.try_number >= 3:
        send_slack_alert(f"Task {ti.task_id} is on retry #{ti.try_number}")
```

---

**Q8. Can you have multiple callbacks on the same task?**

Each callback parameter (`on_failure_callback`, `on_success_callback`, etc.) accepts a single callable. To run multiple functions, wrap them:

```python
def combined_failure_handler(context):
    slack_alert(context)
    email_alert(context)
    pagerduty_alert(context)

task = PythonOperator(
    task_id="critical_task",
    on_failure_callback=combined_failure_handler,
    ...
)
```

---

**Q9. What is the difference between on_failure_callback on a task and on a DAG?**

When set on a task, `on_failure_callback` fires only when that specific task fails. When set on the DAG, it fires whenever any task in the DAG fails. The DAG-level callback is the practical choice for pipeline monitoring — you write the notification function once and it covers the entire pipeline. Task-level callbacks are useful when specific tasks need custom handling (e.g., a critical task triggers PagerDuty while less critical tasks only log to Slack).

---

**Q10. How do you include the error message in a failure callback?**

Access it via `context.get("exception")`:

```python
def my_failure_handler(context):
    exception = context.get("exception")
    error_msg = str(exception) if exception else "No exception details available"
    print(f"Error: {error_msg}")
```

The `exception` key contains the actual Python exception object that caused the failure. Use `str(exception)` to get a human-readable message. Be careful with long stack traces — truncate before sending to chat services like Slack.

---

## Navigation

**Prev:** [17 — Deferrable Operators](../17_Deferrable_Operators/Interview_QA.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [19 — Pools and Resources](../19_Pools_and_Resources/Interview_QA.md)
