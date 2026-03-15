# Monitoring and Alerting — Code Examples

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Pools and Resources](../19_Pools_and_Resources/Theory.md)**

---

## Example 1: StatsD Configuration

StatsD lets Airflow emit metrics to any StatsD-compatible server (Telegraf, StatsD daemon, DogStatsD for Datadog).

```ini
# airflow.cfg
[metrics]
statsd_on = True
statsd_host = statsd-exporter        # hostname of your StatsD server
statsd_port = 8125
statsd_prefix = airflow              # all metrics prefixed with "airflow."

# Optional: allowlist/denylist specific metrics
# statsd_allow_list = scheduler.heartbeat,task.duration,dagrun.duration
# statsd_block_list = scheduler.critical_section_duration
```

Using environment variables:
```bash
export AIRFLOW__METRICS__STATSD_ON=True
export AIRFLOW__METRICS__STATSD_HOST=statsd-exporter
export AIRFLOW__METRICS__STATSD_PORT=8125
export AIRFLOW__METRICS__STATSD_PREFIX=airflow
```

### StatsD in Docker Compose

```yaml
# docker-compose.yml — adds a StatsD exporter + Prometheus scrape target
services:
  statsd-exporter:
    image: prom/statsd-exporter:v0.26.0
    ports:
      - "9102:9102"    # Prometheus scrape endpoint
      - "8125:8125/udp" # StatsD ingestion port
    command:
      - "--statsd.mapping-config=/etc/statsd/mapping.yml"
    volumes:
      - ./statsd_mapping.yml:/etc/statsd/mapping.yml:ro
```

```yaml
# statsd_mapping.yml — map Airflow StatsD metric names to Prometheus labels
mappings:
  - match: "airflow.dag.*.*.duration"
    name: "airflow_dag_duration_seconds"
    labels:
      dag_id: "$1"
      status: "$2"

  - match: "airflow.task.duration"
    name: "airflow_task_duration_seconds"
    labels:
      dag_id: "$1"
      task_id: "$2"

  - match: "airflow.scheduler.heartbeat"
    name: "airflow_scheduler_heartbeat_total"
```

---

## Example 2: Prometheus Metrics Endpoint Configuration

Airflow 3 has a built-in Prometheus metrics endpoint on the API Server. No StatsD exporter needed.

```ini
# airflow.cfg
[metrics]
# Enable the Prometheus endpoint at /metrics on the API Server
metrics_use_pattern_match = True

[api]
# The /metrics endpoint is served by the api-server on the same port as the UI
# It requires authentication — configure an appropriate auth token or
# disable auth for the scrape endpoint using the setting below
auth_backends = airflow.api.auth.backend.basic_auth
```

Prometheus scrape config:
```yaml
# prometheus.yml
scrape_configs:
  - job_name: airflow
    static_configs:
      - targets:
          - "airflow-api-server:8080"
    metrics_path: /metrics
    # Basic auth for Prometheus scrape
    basic_auth:
      username: airflow_metrics
      password: scrape_password
    scrape_interval: 30s
    scrape_timeout: 10s
```

Key metrics exposed:
```
# Scheduler health
airflow_scheduler_heartbeat_total
airflow_scheduler_critical_section_duration_seconds

# Task metrics
airflow_task_duration_seconds{dag_id, task_id, state}
airflow_task_queued_duration_seconds{dag_id, task_id}

# DAG run metrics
airflow_dagrun_duration_seconds{dag_id, state}
airflow_dagrun_schedule_delay_seconds{dag_id}

# Pool metrics
airflow_pool_open_slots{pool_name}
airflow_pool_running_slots{pool_name}
airflow_pool_queued_slots{pool_name}
```

---

## Example 3: Sample Grafana Dashboard Configuration (Abbreviated)

A minimal Grafana dashboard JSON for Airflow monitoring. Import via Grafana UI: + > Import > paste JSON.

```json
{
  "title": "Airflow Monitoring",
  "uid": "airflow-overview",
  "refresh": "30s",
  "panels": [
    {
      "id": 1,
      "title": "Scheduler Heartbeat (last 5 min)",
      "type": "stat",
      "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
      "targets": [
        {
          "expr": "increase(airflow_scheduler_heartbeat_total[5m])",
          "legendFormat": "Heartbeats"
        }
      ],
      "thresholds": {
        "steps": [
          {"color": "red",    "value": 0},
          {"color": "yellow", "value": 1},
          {"color": "green",  "value": 5}
        ]
      }
    },
    {
      "id": 2,
      "title": "Task Success Rate (1h)",
      "type": "gauge",
      "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
      "targets": [
        {
          "expr": "sum(increase(airflow_task_duration_seconds_count{state='success'}[1h])) / sum(increase(airflow_task_duration_seconds_count[1h])) * 100",
          "legendFormat": "Success %"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "min": 0, "max": 100, "unit": "percent",
          "thresholds": {
            "steps": [
              {"color": "red",    "value": 0},
              {"color": "yellow", "value": 90},
              {"color": "green",  "value": 98}
            ]
          }
        }
      }
    },
    {
      "id": 3,
      "title": "Pool Utilization",
      "type": "table",
      "gridPos": {"h": 6, "w": 12, "x": 0, "y": 4},
      "targets": [
        {
          "expr": "airflow_pool_running_slots",
          "legendFormat": "Running: {{pool_name}}"
        },
        {
          "expr": "airflow_pool_queued_slots",
          "legendFormat": "Queued: {{pool_name}}"
        },
        {
          "expr": "airflow_pool_open_slots",
          "legendFormat": "Open: {{pool_name}}"
        }
      ]
    },
    {
      "id": 4,
      "title": "Failed Tasks (24h)",
      "type": "timeseries",
      "gridPos": {"h": 6, "w": 12, "x": 0, "y": 10},
      "targets": [
        {
          "expr": "sum by (dag_id) (increase(airflow_task_duration_seconds_count{state='failed'}[1h]))",
          "legendFormat": "{{dag_id}}"
        }
      ]
    }
  ]
}
```

---

## Example 4: Email Alerting Configuration

```ini
# airflow.cfg
[smtp]
smtp_host = smtp.gmail.com
smtp_starttls = True
smtp_ssl = False
smtp_user = airflow@yourcompany.com
smtp_password = your_app_password
smtp_port = 587
smtp_mail_from = airflow@yourcompany.com
smtp_timeout = 30
smtp_retry_limit = 5
```

Using environment variables:
```bash
export AIRFLOW__SMTP__SMTP_HOST=smtp.gmail.com
export AIRFLOW__SMTP__SMTP_STARTTLS=True
export AIRFLOW__SMTP__SMTP_USER=airflow@yourcompany.com
export AIRFLOW__SMTP__SMTP_PASSWORD=your_app_password
export AIRFLOW__SMTP__SMTP_PORT=587
export AIRFLOW__SMTP__SMTP_MAIL_FROM=airflow@yourcompany.com
```

### Enabling email alerts on a DAG

```python
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

with DAG(
    dag_id="email_alert_demo",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={
        # Email recipients for task failures
        "email": ["oncall@yourcompany.com", "lead@yourcompany.com"],
        "email_on_failure": True,     # Send email when any task fails
        "email_on_retry": False,      # Don't spam on retries
        "retries": 2,
    },
) as dag:

    def might_fail():
        import random
        if random.random() < 0.3:
            raise ValueError("Simulated random failure")
        print("Task succeeded")

    risky_task = PythonOperator(
        task_id="risky_task",
        python_callable=might_fail,
        # Override email settings for this specific task if needed:
        # email=["specific-team@yourcompany.com"],
    )
```

### Sending a custom email from within a task

```python
from airflow.utils.email import send_email

def send_report_email(**context):
    dag_run = context["dag_run"]
    ds      = context["ds"]

    send_email(
        to=["analytics@yourcompany.com"],
        subject=f"Daily Sales Report — {ds}",
        html_content=f"""
        <h2>Daily Sales Report</h2>
        <p>Report for <strong>{ds}</strong> has been generated.</p>
        <p>DAG Run ID: {dag_run.run_id}</p>
        <p>View in <a href="http://airflow.yourcompany.com/dags/sales_pipeline/grid">Airflow UI</a></p>
        """,
    )
```

---

## Example 5: Slack Webhook Callback

```python
# dags/slack_alerting_demo.py
"""
DAG with Slack alerts on failure and success.
Requires the Airflow SMTP or HTTP connection to Slack Webhook.
"""
import requests
import os
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime


SLACK_WEBHOOK_URL = os.environ.get(
    "SLACK_WEBHOOK_URL",
    "https://hooks.slack.com/services/T000/B000/xxxx"
)


def notify_slack_failure(context):
    """Callback for on_failure_callback — sends a Slack alert."""
    dag_id   = context["dag"].dag_id
    task_id  = context["task_instance"].task_id
    run_id   = context["dag_run"].run_id
    log_url  = context["task_instance"].log_url

    message = {
        "text": f":red_circle: *Task Failed*",
        "attachments": [
            {
                "color": "#FF0000",
                "fields": [
                    {"title": "DAG",     "value": dag_id,  "short": True},
                    {"title": "Task",    "value": task_id, "short": True},
                    {"title": "Run ID",  "value": run_id,  "short": False},
                    {"title": "Logs",    "value": log_url, "short": False},
                ],
            }
        ],
    }
    requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)


def notify_slack_success(context):
    """Callback for on_success_callback — sends a Slack success notification."""
    dag_id  = context["dag"].dag_id
    run_id  = context["dag_run"].run_id

    message = {
        "text": f":white_check_mark: *DAG Succeeded*: `{dag_id}` (run: `{run_id}`)"
    }
    requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)


with DAG(
    dag_id="slack_alerting_demo",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    on_failure_callback=notify_slack_failure,   # DAG-level — fires if ANY task fails
    on_success_callback=notify_slack_success,   # DAG-level — fires when DAG completes
) as dag:

    def extract():
        print("Extracting...")

    def transform():
        raise ValueError("Intentional failure for demo purposes")

    extract_task   = PythonOperator(task_id="extract",   python_callable=extract)
    transform_task = PythonOperator(
        task_id="transform",
        python_callable=transform,
        # Task-level callback — only fires for this specific task
        on_failure_callback=notify_slack_failure,
        retries=1,
    )

    extract_task >> transform_task
```

---

## Example 6: Custom Metrics with StatsD Client

You can emit your own business metrics from within task code alongside Airflow's built-in metrics.

```python
# dags/custom_metrics_demo.py
"""
Emitting custom business metrics via StatsD from inside task code.

These metrics appear in the same StatsD/Prometheus pipeline as Airflow's
built-in metrics, letting you correlate business KPIs with pipeline health.
"""
from airflow.sdk import DAG
from airflow.decorators import task
from datetime import datetime


@task
def process_orders(**context):
    """Processes orders and emits custom metrics via StatsD."""
    from statsd import StatsClient

    # Connect to the same StatsD server Airflow uses
    statsd = StatsClient(
        host="statsd-exporter",
        port=8125,
        prefix=f"airflow.custom.{context['dag'].dag_id}"
    )

    # Simulate processing
    orders_processed = 15_000
    orders_failed    = 42
    total_revenue    = 128_500.75
    processing_time  = 23.4  # seconds

    # ── Emit counters ─────────────────────────────────────────────────────────
    statsd.incr("orders.processed", orders_processed)
    statsd.incr("orders.failed", orders_failed)

    # ── Emit gauges (current value) ───────────────────────────────────────────
    statsd.gauge("revenue.daily_total", total_revenue)
    statsd.gauge("orders.success_rate",
                 (orders_processed - orders_failed) / orders_processed * 100)

    # ── Emit timing ───────────────────────────────────────────────────────────
    statsd.timing("processing_duration_ms", processing_time * 1000)

    # ── Context manager for timing a code block ───────────────────────────────
    with statsd.timer("database_write_ms"):
        import time
        time.sleep(0.5)   # Simulated DB write
        print("Writing to database...")

    print(f"Processed {orders_processed} orders, revenue: ${total_revenue:,.2f}")
    return {"processed": orders_processed, "revenue": total_revenue}


with DAG(
    dag_id="custom_metrics_demo",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    process_orders()
```

Install the StatsD client library:
```bash
pip install statsd
```

The metrics appear in Grafana under names like:
```
airflow.custom.custom_metrics_demo.orders.processed
airflow.custom.custom_metrics_demo.revenue.daily_total
airflow.custom.custom_metrics_demo.processing_duration_ms
```

---

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Pools and Resources](../19_Pools_and_Resources/Theory.md)**
