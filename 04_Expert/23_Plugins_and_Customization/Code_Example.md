# 23 — Plugins and Customization: Code Examples

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: Custom Macro Plugin — Date Formatting Helpers

A plugin that adds useful date manipulation macros available in all DAG templates.

```python
# plugins/date_macros_plugin.py
"""
Date utility macros for Airflow DAG templates.

Usage in DAG templates:
    {{ macros.date_macros.format_ds(ds, '%B %d, %Y') }}
    → "March 15, 2026"

    {{ macros.date_macros.ds_add_days(ds, -7) }}
    → "2026-03-08"

    {{ macros.date_macros.ds_in_timezone(ds, 'America/New_York') }}
    → "2026-03-14T20:00:00-04:00"

    {{ macros.date_macros.ds_is_business_day(ds) }}
    → True or False

    {{ macros.date_macros.month_start(ds) }}
    → "2026-03-01"
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytz

from airflow.plugins_manager import AirflowPlugin


def format_ds(ds: str, fmt: str) -> str:
    """
    Reformat an execution date string from YYYY-MM-DD into any strftime format.

    Args:
        ds:  Execution date in YYYY-MM-DD format (e.g., {{ ds }})
        fmt: Target strftime format string

    Returns:
        Formatted date string

    Example:
        {{ macros.date_macros.format_ds(ds, '%d/%m/%Y') }}  → "15/03/2026"
    """
    return datetime.strptime(ds, "%Y-%m-%d").strftime(fmt)


def ds_add_days(ds: str, days: int) -> str:
    """
    Add (or subtract) days from an execution date string.

    Args:
        ds:   Execution date in YYYY-MM-DD format
        days: Number of days to add (negative to subtract)

    Returns:
        New date string in YYYY-MM-DD format

    Example:
        {{ macros.date_macros.ds_add_days(ds, -1) }}  → yesterday
    """
    dt = datetime.strptime(ds, "%Y-%m-%d")
    return (dt + timedelta(days=days)).strftime("%Y-%m-%d")


def ds_in_timezone(ds: str, tz_name: str) -> str:
    """
    Convert a YYYY-MM-DD execution date (assumed UTC midnight) to a
    timezone-aware ISO 8601 string.

    Args:
        ds:      Execution date in YYYY-MM-DD format
        tz_name: IANA timezone name (e.g., 'America/New_York', 'Europe/London')

    Returns:
        ISO 8601 string with UTC offset

    Example:
        {{ macros.date_macros.ds_in_timezone(ds, 'US/Pacific') }}
    """
    utc_dt = datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
    local_tz = pytz.timezone(tz_name)
    return utc_dt.astimezone(local_tz).isoformat()


def ds_is_business_day(ds: str) -> bool:
    """
    Return True if the execution date falls on a weekday (Mon–Fri).

    Example:
        {% if macros.date_macros.ds_is_business_day(ds) %}
            ... run business logic ...
        {% endif %}
    """
    dt = datetime.strptime(ds, "%Y-%m-%d")
    return dt.weekday() < 5  # 0=Monday, 4=Friday


def month_start(ds: str) -> str:
    """
    Return the first day of the month of the execution date.

    Example:
        {{ macros.date_macros.month_start(ds) }}  → "2026-03-01"
    """
    dt = datetime.strptime(ds, "%Y-%m-%d")
    return dt.replace(day=1).strftime("%Y-%m-%d")


def month_end(ds: str) -> str:
    """
    Return the last day of the month of the execution date.
    Uses a month-rollover trick: first day of next month minus one day.

    Example:
        {{ macros.date_macros.month_end(ds) }}  → "2026-03-31"
    """
    dt = datetime.strptime(ds, "%Y-%m-%d")
    # Advance to first of next month, subtract one day
    if dt.month == 12:
        last = dt.replace(year=dt.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
    return last.strftime("%Y-%m-%d")


class DateMacrosPlugin(AirflowPlugin):
    name = "date_macros"
    macros = [format_ds, ds_add_days, ds_in_timezone, ds_is_business_day, month_start, month_end]
```

### Usage in a DAG

```python
# dags/reporting_dag.py
from airflow.sdk import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from datetime import datetime

with DAG(
    dag_id="monthly_report",
    schedule="0 6 1 * *",  # First of each month
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    run_report = SQLExecuteQueryOperator(
        task_id="run_monthly_report",
        conn_id="postgres_default",
        # Macros are resolved at runtime
        sql="""
            SELECT *
            FROM transactions
            WHERE created_at BETWEEN '{{ macros.date_macros.month_start(ds) }}'
                              AND '{{ macros.date_macros.month_end(ds) }}'
        """,
    )
```

---

## Example 2: Custom UI Page with AppBuilderBaseView

A "Pipeline Health" dashboard page embedded in the Airflow UI, showing recent DAG run statistics.

```python
# plugins/pipeline_health_plugin.py
"""
Adds a "Pipeline Health" page to the Airflow UI under the Browse menu.
Shows aggregate statistics for the last 24 hours.

Navigation: Browse → Pipeline Health
URL: /pipelinehealthview/
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint
from flask_appbuilder import expose
from flask_appbuilder.baseviews import BaseView as AppBuilderBaseView

from airflow.plugins_manager import AirflowPlugin
from airflow.utils.session import create_session

# Blueprint required for static files / templates
health_bp = Blueprint(
    "pipeline_health_bp",
    __name__,
    template_folder="templates",
)


class PipelineHealthView(AppBuilderBaseView):
    """Dashboard showing aggregate pipeline health for the last 24 hours."""

    default_view = "index"
    route_base = "/pipelinehealthview"

    @expose("/")
    def index(self):
        stats = self._get_stats(hours=24)
        return self.render_template(
            "pipeline_health.html",
            stats=stats,
            window_hours=24,
        )

    @expose("/weekly")
    def weekly(self):
        stats = self._get_stats(hours=168)
        return self.render_template(
            "pipeline_health.html",
            stats=stats,
            window_hours=168,
        )

    def _get_stats(self, hours: int = 24) -> dict:
        """Query metadata DB for aggregate stats over the past N hours."""
        from airflow.models import DagRun, TaskInstance
        from airflow.utils.state import DagRunState, TaskInstanceState

        cutoff = datetime.utcnow() - timedelta(hours=hours)

        with create_session() as session:
            total_runs = (
                session.query(DagRun)
                .filter(DagRun.execution_date >= cutoff)
                .count()
            )
            successful_runs = (
                session.query(DagRun)
                .filter(
                    DagRun.execution_date >= cutoff,
                    DagRun.state == DagRunState.SUCCESS,
                )
                .count()
            )
            failed_runs = (
                session.query(DagRun)
                .filter(
                    DagRun.execution_date >= cutoff,
                    DagRun.state == DagRunState.FAILED,
                )
                .count()
            )
            failed_tasks = (
                session.query(TaskInstance)
                .filter(
                    TaskInstance.end_date >= cutoff,
                    TaskInstance.state == TaskInstanceState.FAILED,
                )
                .order_by(TaskInstance.end_date.desc())
                .limit(20)
                .all()
            )

        success_rate = (
            round(successful_runs / total_runs * 100, 1) if total_runs > 0 else 0
        )

        return {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "success_rate": success_rate,
            "failed_tasks": failed_tasks,
        }


class PipelineHealthPlugin(AirflowPlugin):
    name = "pipeline_health"
    flask_blueprints = [health_bp]
    appbuilder_views = [{"view": PipelineHealthView()}]
    appbuilder_menu_items = [
        {
            "name": "Pipeline Health",
            "category": "Browse",
            "category_icon": "fa-heartbeat",
            "href": "/pipelinehealthview/",
        }
    ]
```

Template at `plugins/templates/pipeline_health.html`:
```html
{% extends "airflow/main.html" %}
{% block content %}
<div class="container">
  <h2>Pipeline Health — Last {{ window_hours }}h</h2>

  <div class="row">
    <div class="col-md-3">
      <div class="panel panel-default">
        <div class="panel-body text-center">
          <h1>{{ stats.total_runs }}</h1>
          <p>Total Runs</p>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="panel panel-success">
        <div class="panel-body text-center">
          <h1>{{ stats.successful_runs }}</h1>
          <p>Successful</p>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="panel panel-danger">
        <div class="panel-body text-center">
          <h1>{{ stats.failed_runs }}</h1>
          <p>Failed</p>
        </div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="panel panel-info">
        <div class="panel-body text-center">
          <h1>{{ stats.success_rate }}%</h1>
          <p>Success Rate</p>
        </div>
      </div>
    </div>
  </div>

  <h3>Recent Failures</h3>
  <table class="table table-striped">
    <thead>
      <tr>
        <th>DAG</th><th>Task</th><th>Run ID</th><th>Failed At</th>
      </tr>
    </thead>
    <tbody>
      {% for ti in stats.failed_tasks %}
      <tr>
        <td><a href="/dags/{{ ti.dag_id }}/grid">{{ ti.dag_id }}</a></td>
        <td>{{ ti.task_id }}</td>
        <td>{{ ti.run_id }}</td>
        <td>{{ ti.end_date.strftime('%Y-%m-%d %H:%M:%S') if ti.end_date else '-' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <a href="/pipelinehealthview/weekly" class="btn btn-default">View 7-Day Stats</a>
</div>
{% endblock %}
```

---

## Example 3: Listener That Logs All Task State Changes

A comprehensive listener that captures all task lifecycle events, writes structured logs, and can be extended with alerting integrations.

```python
# plugins/observability_listener_plugin.py
"""
Platform-wide observability listener.

Captures every task state change across all DAGs and emits structured
log lines. Designed to be extended with metrics emission (StatsD,
Prometheus) or alerting (PagerDuty, Slack).

To enable: drop this file in $AIRFLOW_HOME/plugins/ — no DAG changes needed.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

from airflow.listeners import hookimpl
from airflow.plugins_manager import AirflowPlugin

if TYPE_CHECKING:
    from airflow.models.dagrun import DagRun
    from airflow.models.taskinstance import TaskInstance

log = logging.getLogger("airflow.observability")


def _task_event(event: str, task_instance: "TaskInstance", extra: dict | None = None) -> dict:
    """Build a structured event dict from a TaskInstance."""
    payload = {
        "event": event,
        "timestamp": datetime.utcnow().isoformat(),
        "dag_id": task_instance.dag_id,
        "task_id": task_instance.task_id,
        "run_id": task_instance.run_id,
        "try_number": task_instance.try_number,
        "hostname": task_instance.hostname,
        "operator": task_instance.operator,
        "queue": task_instance.queue,
        "pool": task_instance.pool,
        "duration_seconds": (
            round(task_instance.duration, 3) if task_instance.duration else None
        ),
        "execution_date": str(task_instance.logical_date) if hasattr(task_instance, "logical_date") else None,
    }
    if extra:
        payload.update(extra)
    return payload


def _dag_event(event: str, dag_run: "DagRun", msg: str = "") -> dict:
    """Build a structured event dict from a DagRun."""
    return {
        "event": event,
        "timestamp": datetime.utcnow().isoformat(),
        "dag_id": dag_run.dag_id,
        "run_id": dag_run.run_id,
        "run_type": dag_run.run_type,
        "logical_date": str(dag_run.logical_date) if dag_run.logical_date else None,
        "message": msg,
    }


class ObservabilityListener:
    """
    Listens to all task and DAG run state transitions.

    Extend _emit() to send events to your metrics/alerting stack:
        - StatsD / DogStatsD
        - Prometheus pushgateway
        - Slack / PagerDuty
        - Splunk / Datadog
        - Internal audit database
    """

    # -----------------------------------------------------------------
    # Task lifecycle hooks
    # -----------------------------------------------------------------

    @hookimpl
    def on_task_instance_running(
        self,
        previous_state,
        task_instance: "TaskInstance",
        session,
    ) -> None:
        event = _task_event(
            "task_running",
            task_instance,
            extra={"previous_state": str(previous_state)},
        )
        self._emit(event)
        log.info("TASK_RUNNING %s", json.dumps(event))

    @hookimpl
    def on_task_instance_success(
        self,
        previous_state,
        task_instance: "TaskInstance",
        session,
    ) -> None:
        event = _task_event("task_success", task_instance)
        self._emit(event)
        log.info("TASK_SUCCESS %s", json.dumps(event))

    @hookimpl
    def on_task_instance_failed(
        self,
        previous_state,
        task_instance: "TaskInstance",
        session,
    ) -> None:
        event = _task_event(
            "task_failed",
            task_instance,
            extra={
                "previous_state": str(previous_state),
                "map_index": getattr(task_instance, "map_index", -1),
            },
        )
        self._emit(event)
        log.error("TASK_FAILED %s", json.dumps(event))

        # Example: send alert for critical DAGs
        if task_instance.dag_id.startswith("critical_"):
            self._send_critical_alert(task_instance)

    # -----------------------------------------------------------------
    # DAG run lifecycle hooks
    # -----------------------------------------------------------------

    @hookimpl
    def on_dag_run_running(
        self,
        dag_run: "DagRun",
        msg: str,
        session,
    ) -> None:
        event = _dag_event("dagrun_running", dag_run, msg)
        self._emit(event)
        log.info("DAGRUN_RUNNING %s", json.dumps(event))

    @hookimpl
    def on_dag_run_success(
        self,
        dag_run: "DagRun",
        msg: str,
        session,
    ) -> None:
        event = _dag_event("dagrun_success", dag_run, msg)
        self._emit(event)
        log.info("DAGRUN_SUCCESS %s", json.dumps(event))

    @hookimpl
    def on_dag_run_failed(
        self,
        dag_run: "DagRun",
        msg: str,
        session,
    ) -> None:
        event = _dag_event("dagrun_failed", dag_run, msg)
        self._emit(event)
        log.error("DAGRUN_FAILED %s", json.dumps(event))

    # -----------------------------------------------------------------
    # Extension points
    # -----------------------------------------------------------------

    def _emit(self, event: dict) -> None:
        """
        Override this method to send events to external systems.

        Example StatsD integration:
            from statsd import StatsClient
            statsd = StatsClient()
            if event["event"] == "task_success":
                statsd.incr(f"airflow.task.success.{event['dag_id']}.{event['task_id']}")
                if event["duration_seconds"]:
                    statsd.timing(
                        f"airflow.task.duration.{event['dag_id']}.{event['task_id']}",
                        event["duration_seconds"] * 1000,
                    )
        """
        pass  # Base implementation: structured logging only (see log.info/log.error calls)

    def _send_critical_alert(self, task_instance: "TaskInstance") -> None:
        """
        Send a high-priority alert for failures in critical DAGs.
        Implement with PagerDuty, Slack, etc.
        """
        log.critical(
            "CRITICAL_DAG_FAILURE dag=%s task=%s run=%s",
            task_instance.dag_id,
            task_instance.task_id,
            task_instance.run_id,
        )
        # Example: POST to Slack webhook
        # import requests
        # requests.post(SLACK_WEBHOOK_URL, json={
        #     "text": f":red_circle: Critical DAG failure: {task_instance.dag_id}.{task_instance.task_id}"
        # })


class ObservabilityPlugin(AirflowPlugin):
    name = "observability"
    listeners = [ObservabilityListener()]
```

### Verifying the Listener Works

```bash
# Check plugin was loaded
airflow plugins list

# Trigger a DAG and watch the scheduler logs for TASK_RUNNING / TASK_SUCCESS entries
airflow dags trigger my_dag

# View scheduler logs
tail -f $AIRFLOW_HOME/logs/scheduler/latest/my_dag.py.log | grep -E "TASK_(RUNNING|SUCCESS|FAILED)"
```
