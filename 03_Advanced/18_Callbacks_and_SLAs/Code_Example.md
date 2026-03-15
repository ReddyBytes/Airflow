# 18 — Callbacks and SLAs: Code Examples

---

## Example 1: Slack Failure Notification

A reusable Slack alert callback with rich formatting.

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta


# ── Callback function ────────────────────────────────────────────────────────

def slack_failure_alert(context: dict) -> None:
    """
    Sends a formatted Slack message when any task fails.
    Requires: Slack Webhook connection configured in Airflow as 'slack_webhook_alerts'
    Install:  pip install apache-airflow-providers-slack
    """
    from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook

    ti           = context["task_instance"]
    logical_date = context.get("logical_date", "N/A")
    exception    = context.get("exception")
    error_text   = str(exception)[:500] if exception else "No exception details"

    # Construct rich Slack message with Block Kit formatting
    message = (
        f":red_circle: *Pipeline Task Failed*\n"
        f"*DAG:*    `{ti.dag_id}`\n"
        f"*Task:*   `{ti.task_id}`\n"
        f"*Run ID:* `{ti.run_id}`\n"
        f"*Date:*   `{logical_date}`\n"
        f"*Attempt:* #{ti.try_number}\n"
        f"\n"
        f"*Error:*\n```{error_text}```\n"
        f"\n"
        f"<https://airflow.example.com/dags/{ti.dag_id}/grid|View in Airflow>"
    )

    hook = SlackWebhookHook(slack_webhook_conn_id="slack_webhook_alerts")
    hook.send(text=message)


# ── DAG using the callback ───────────────────────────────────────────────────

def extract_data(**context):
    raise ValueError("Connection refused: database unreachable")  # Simulated failure


def transform_data(**context):
    pass


with DAG(
    dag_id="slack_callback_example",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
        # Apply failure callback to every task via default_args
        "on_failure_callback": slack_failure_alert,
    },
    tags=["example", "callbacks"],
) as dag:

    extract = PythonOperator(
        task_id="extract",
        python_callable=extract_data,
    )

    transform = PythonOperator(
        task_id="transform",
        python_callable=transform_data,
    )

    extract >> transform
```

---

## Example 2: Email Notification on Retry

Alert when a task retries — useful for detecting flapping tasks before they exhaust all retries.

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.email import send_email
from datetime import datetime, timedelta
import logging


def email_on_retry(context: dict) -> None:
    """Send email when a task retries. Only pages on 2nd+ retry to avoid noise."""
    ti         = context["task_instance"]
    attempt    = ti.try_number
    exception  = context.get("exception")

    # Only alert on 2nd retry and beyond — first retry might be a transient blip
    if attempt < 2:
        logging.info(f"First retry for {ti.task_id} — not alerting yet.")
        return

    send_email(
        to=["data-engineering@example.com"],
        subject=f"[Airflow RETRY #{attempt}] {ti.dag_id} / {ti.task_id}",
        html_content=f"""
        <h2 style="color: orange;">Task Retry Alert</h2>
        <table>
            <tr><td><b>DAG:</b></td><td>{ti.dag_id}</td></tr>
            <tr><td><b>Task:</b></td><td>{ti.task_id}</td></tr>
            <tr><td><b>Run ID:</b></td><td>{ti.run_id}</td></tr>
            <tr><td><b>Attempt:</b></td><td>{attempt}</td></tr>
            <tr><td><b>Logical Date:</b></td><td>{context.get('logical_date')}</td></tr>
            <tr><td><b>Exception:</b></td><td><pre>{str(exception)[:1000]}</pre></td></tr>
        </table>
        <p>The task is being retried. If it fails {ti.max_tries - attempt + 1} more time(s),
           it will be marked FAILED.</p>
        """,
    )
    logging.info(f"Retry email sent for attempt #{attempt}")


def flaky_api_call(**context):
    """Simulates a task that fails a few times before succeeding."""
    import random
    if random.random() < 0.7:
        raise ConnectionError("Upstream API returned 503")
    logging.info("API call succeeded!")


with DAG(
    dag_id="email_on_retry_example",
    start_date=datetime(2024, 1, 1),
    schedule="@hourly",
    catchup=False,
    tags=["example", "callbacks"],
) as dag:

    api_task = PythonOperator(
        task_id="call_external_api",
        python_callable=flaky_api_call,
        retries=3,
        retry_delay=timedelta(minutes=2),
        on_retry_callback=email_on_retry,
    )
```

---

## Example 3: SLA Miss Handler

Notify when a task takes too long relative to its scheduled time.

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import logging


def sla_miss_notifier(dag, task_list, blocking_task_list, slas, blocking_tis):
    """
    Called when any task in the DAG misses its SLA.
    Note: this has a different signature from on_failure_callback.
    """
    logging.warning(f"SLA MISS in DAG: {dag.dag_id}")
    logging.warning(f"Tasks that missed SLA: {task_list}")
    logging.warning(f"Blocking tasks: {blocking_task_list}")

    # Build details for each miss
    for sla_miss in slas:
        logging.warning(
            f"  Task '{sla_miss.task_id}' missed SLA. "
            f"Execution: {sla_miss.execution_date}. "
            f"Reported at: {sla_miss.timestamp}"
        )

    # In production, send to Slack or PagerDuty
    # Example: send_slack_alert(f"SLA missed in {dag.dag_id}: {task_list}")

    # You could also inspect blocking_tis for more details
    for ti in blocking_tis:
        logging.warning(
            f"  Blocking task: {ti.task_id} "
            f"in state: {ti.state} "
            f"started: {ti.start_date}"
        )


def slow_transformation(**context):
    """Simulates a slow task that will miss its 1-minute SLA."""
    import time
    logging.info("Running slow transformation...")
    time.sleep(90)   # Takes 90 seconds — will miss a 1-minute SLA
    logging.info("Transformation complete.")


with DAG(
    dag_id="sla_miss_example",
    start_date=datetime(2024, 1, 1),
    schedule="@hourly",
    catchup=False,
    # SLA miss callback is ONLY valid at the DAG level
    sla_miss_callback=sla_miss_notifier,
    tags=["example", "sla"],
) as dag:

    transform = PythonOperator(
        task_id="slow_transform",
        python_callable=slow_transformation,
        # SLA: this task must complete within 1 minute of the logical date
        sla=timedelta(minutes=1),
    )
```

**Note:** SLA miss detection runs on the scheduler's heartbeat cycle — there may be a short delay between the actual miss and the callback firing.

---

## Example 4: Full DAG with All Callbacks Wired

A production-ready pattern with failure alerts, retry alerts, SLA monitoring, and success tracking.

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.email import send_email
from datetime import datetime, timedelta
import logging


# ── Callback library ─────────────────────────────────────────────────────────

def send_slack(message: str, channel: str = "#data-alerts") -> None:
    """Wrapper to send Slack messages. Replace with your actual hook."""
    logging.info(f"[Slack → {channel}] {message}")
    # In production:
    # from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook
    # SlackWebhookHook(slack_webhook_conn_id="slack_alerts").send(text=message)


def on_task_failure(context: dict) -> None:
    ti        = context["task_instance"]
    exception = context.get("exception", "")
    send_slack(
        f":red_circle: FAILED | {ti.dag_id}.{ti.task_id} | "
        f"Run: {ti.run_id} | Error: {str(exception)[:200]}"
    )


def on_task_success(context: dict) -> None:
    ti = context["task_instance"]
    # Only log success for certain critical tasks — avoid noise
    logging.info(f"Task {ti.task_id} succeeded in run {ti.run_id}")


def on_task_retry(context: dict) -> None:
    ti = context["task_instance"]
    if ti.try_number >= 2:
        send_slack(
            f":warning: RETRY #{ti.try_number} | {ti.dag_id}.{ti.task_id} | "
            f"Run: {ti.run_id}"
        )


def on_sla_miss(dag, task_list, blocking_task_list, slas, blocking_tis):
    send_slack(
        f":hourglass_flowing_sand: SLA MISS | {dag.dag_id} | "
        f"Tasks: {task_list} | Blocked by: {blocking_task_list}",
        channel="#data-sla-alerts",
    )


# ── DAG definition ───────────────────────────────────────────────────────────

def extract(**context):
    logging.info("Extracting data from source systems...")

def validate(**context):
    logging.info("Validating schema and data quality...")

def transform(**context):
    logging.info("Applying business transformations...")

def load(**context):
    logging.info("Loading data to production tables...")

def notify(**context):
    ti  = context["task_instance"]
    run = context["dag_run"]
    send_slack(
        f":white_check_mark: PIPELINE COMPLETE | {ti.dag_id} | "
        f"Run: {run.run_id} | Date: {context['logical_date']}",
        channel="#data-success",
    )


with DAG(
    dag_id="full_callbacks_example",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    # DAG-level callbacks — fire for every task
    on_failure_callback=on_task_failure,
    on_retry_callback=on_task_retry,
    sla_miss_callback=on_sla_miss,
    default_args={
        "retries":      2,
        "retry_delay":  timedelta(minutes=5),
        "sla":          timedelta(hours=3),   # All tasks must finish within 3h
    },
    tags=["example", "callbacks", "production"],
) as dag:

    t_extract = PythonOperator(
        task_id="extract",
        python_callable=extract,
    )

    t_validate = PythonOperator(
        task_id="validate",
        python_callable=validate,
        # Override SLA for this specific task — must finish within 30 min
        sla=timedelta(minutes=30),
    )

    t_transform = PythonOperator(
        task_id="transform",
        python_callable=transform,
    )

    t_load = PythonOperator(
        task_id="load",
        python_callable=load,
    )

    t_notify = PythonOperator(
        task_id="notify_success",
        python_callable=notify,
        # Only the final notify task has on_success_callback
        on_success_callback=on_task_success,
    )

    t_extract >> t_validate >> t_transform >> t_load >> t_notify
```

**What fires and when:**
- Any task fails → `on_task_failure` → Slack alert to #data-alerts
- Any task retries (2nd+ attempt) → `on_task_retry` → Slack warning
- Any task misses 3h SLA → `on_sla_miss` → Slack alert to #data-sla-alerts
- `validate` misses 30min SLA → same `on_sla_miss` (task-level SLA overrides default)
- `notify_success` completes → `on_task_success` → logged (quiet success)

---

## Navigation

**Prev:** [17 — Deferrable Operators](../17_Deferrable_Operators/Code_Example.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [19 — Pools and Resources](../19_Pools_and_Resources/Code_Example.md)
