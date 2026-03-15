# 24 — Custom Operators and Hooks: Custom Sensor Example

## DatabaseRowSensor

A production sensor that polls a database until a row matching specified criteria appears, with both standard `reschedule` mode and a fully deferrable version.

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Use Case

Wait for a control record to appear in a database table before starting downstream processing. This is a common pattern in ETL systems where an upstream job writes a "load complete" record when it finishes.

```sql
-- Upstream job writes this when done:
INSERT INTO etl_control (pipeline_name, run_date, status, row_count, created_at)
VALUES ('orders_daily', '2026-03-15', 'COMPLETE', 95432, NOW());

-- Sensor waits until this row exists with status='COMPLETE'
```

---

## Standard Sensor (reschedule mode)

```python
# sensors/database_row_sensor.py
"""
Sensor that waits until a row matching given criteria exists in a database table.

Designed for polling ETL control tables, data availability checks, and
any scenario where a database record signals readiness.

Example usage:
    wait_for_orders = DatabaseRowSensor(
        task_id="wait_for_orders_load",
        conn_id="postgres_warehouse",
        table="etl_control",
        filter_criteria="pipeline_name = 'orders_daily' AND run_date = '{{ ds }}' AND status = 'COMPLETE'",
        poke_interval=300,          # check every 5 minutes
        timeout=7200,               # fail after 2 hours
        mode="reschedule",          # release worker slot between pokes
    )
"""
from __future__ import annotations

import logging
from typing import Any

from airflow.sensors.base import BaseSensorOperator
from airflow.utils.context import Context

log = logging.getLogger(__name__)


class DatabaseRowSensor(BaseSensorOperator):
    """
    Polls a database table until at least one row matching filter_criteria exists.

    Supports any database with an Airflow DbApiHook-compatible connection
    (PostgreSQL, MySQL, SQLite, Snowflake, etc.).

    :param conn_id:          Airflow connection ID (any DbApiHook-compatible DB)
    :param table:            Table name to query (supports schema prefix: "myschema.mytable")
    :param filter_criteria:  SQL WHERE clause (without the WHERE keyword). Templatable.
                             Example: "pipeline_name = 'orders' AND run_date = '{{ ds }}'"
    :param check_column:     Optional column to SELECT and return as XCom value.
                             If None, does COUNT(*) check.
    :param min_row_count:    Minimum number of matching rows required (default: 1)
    """

    template_fields = ("filter_criteria", "table")
    ui_color = "#a8d8ea"  # Light blue — "waiting"

    def __init__(
        self,
        conn_id: str,
        table: str,
        filter_criteria: str,
        check_column: str | None = None,
        min_row_count: int = 1,
        **kwargs,
    ) -> None:
        # Default to reschedule mode — caller can override but shouldn't use poke in prod
        kwargs.setdefault("mode", "reschedule")
        super().__init__(**kwargs)
        self.conn_id = conn_id
        self.table = table
        self.filter_criteria = filter_criteria
        self.check_column = check_column
        self.min_row_count = min_row_count

    def poke(self, context: Context) -> bool:
        """
        Execute a COUNT query. Returns True if matching row count >= min_row_count.

        Pushes the found row count to XCom key 'row_count' on success.
        """
        from airflow.hooks.dbapi import DbApiHook

        hook = DbApiHook.get_hook(conn_id=self.conn_id)

        if self.check_column:
            sql = (
                f"SELECT {self.check_column} "
                f"FROM {self.table} "
                f"WHERE {self.filter_criteria} "
                f"LIMIT {self.min_row_count}"
            )
        else:
            sql = (
                f"SELECT COUNT(*) "
                f"FROM {self.table} "
                f"WHERE {self.filter_criteria}"
            )

        log.info(
            "DatabaseRowSensor polling: %s | filter: %s",
            self.table,
            self.filter_criteria,
        )
        log.debug("Executing SQL: %s", sql)

        try:
            records = hook.get_records(sql)
        except Exception as e:
            log.error("Database query failed: %s", e)
            # Don't raise — return False to retry on next poke interval
            # Unless it's a connection error we can't recover from
            if "connection" in str(e).lower():
                raise
            return False

        if self.check_column:
            count = len(records)
        else:
            count = records[0][0] if records else 0

        log.info(
            "DatabaseRowSensor result: %d row(s) found (min required: %d)",
            count,
            self.min_row_count,
        )

        if count >= self.min_row_count:
            # Push row count to XCom so downstream tasks can use it
            context["task_instance"].xcom_push(key="row_count", value=count)
            return True
        return False
```

---

## Deferrable Version

The deferrable sensor suspends the task entirely between polls, using zero worker slots while waiting. Requires the Triggerer component.

```python
# sensors/deferrable_database_row_sensor.py
"""
Deferrable version of DatabaseRowSensor.

Requires the Airflow Triggerer component to be running.
Uses no worker slots between poke attempts — ideal for Kubernetes deployments
where worker pods have limited resources.

Usage:
    wait_for_data = DeferrableDatabaseRowSensor(
        task_id="wait_for_data",
        conn_id="postgres_warehouse",
        table="etl_control",
        filter_criteria="pipeline_name = 'orders' AND run_date = '{{ ds }}'",
        poke_interval=300,
        timeout=7200,
    )
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, AsyncIterator

from airflow.sensors.base import BaseSensorOperator
from airflow.triggers.base import BaseTrigger, TriggerEvent
from airflow.utils.context import Context

log = logging.getLogger(__name__)


class DatabaseRowTrigger(BaseTrigger):
    """
    Async trigger that polls a database for a row.

    Runs in the Triggerer process, not a worker.
    Uses async sleep — does not block the event loop.
    """

    def __init__(
        self,
        conn_id: str,
        table: str,
        filter_criteria: str,
        min_row_count: int,
        poll_interval: float,
        timeout_seconds: float,
    ) -> None:
        super().__init__()
        self.conn_id = conn_id
        self.table = table
        self.filter_criteria = filter_criteria
        self.min_row_count = min_row_count
        self.poll_interval = poll_interval
        self.timeout_seconds = timeout_seconds

    def serialize(self) -> tuple[str, dict[str, Any]]:
        """Serialize trigger state for persistence (e.g., after scheduler restart)."""
        return (
            "sensors.deferrable_database_row_sensor.DatabaseRowTrigger",
            {
                "conn_id": self.conn_id,
                "table": self.table,
                "filter_criteria": self.filter_criteria,
                "min_row_count": self.min_row_count,
                "poll_interval": self.poll_interval,
                "timeout_seconds": self.timeout_seconds,
            },
        )

    async def run(self) -> AsyncIterator[TriggerEvent]:
        """
        Main trigger loop. Fires a TriggerEvent when the row is found
        or when timeout is exceeded.
        """
        import asyncio
        import time

        start_time = time.monotonic()
        sql = (
            f"SELECT COUNT(*) FROM {self.table} WHERE {self.filter_criteria}"
        )

        log.info(
            "DatabaseRowTrigger starting: table=%s, poll_interval=%ss",
            self.table,
            self.poll_interval,
        )

        while True:
            elapsed = time.monotonic() - start_time

            if elapsed > self.timeout_seconds:
                yield TriggerEvent(
                    {"status": "timeout", "elapsed_seconds": elapsed}
                )
                return

            count = await self._query_count(sql)
            log.info(
                "DatabaseRowTrigger poll: found %d rows (need %d) after %.0fs",
                count,
                self.min_row_count,
                elapsed,
            )

            if count >= self.min_row_count:
                yield TriggerEvent(
                    {"status": "found", "row_count": count, "elapsed_seconds": elapsed}
                )
                return

            await asyncio.sleep(self.poll_interval)

    async def _query_count(self, sql: str) -> int:
        """Execute COUNT query asynchronously using run_in_executor."""
        loop = asyncio.get_event_loop()

        def _sync_query():
            from airflow.hooks.dbapi import DbApiHook
            hook = DbApiHook.get_hook(conn_id=self.conn_id)
            records = hook.get_records(sql)
            return records[0][0] if records else 0

        try:
            return await loop.run_in_executor(None, _sync_query)
        except Exception as e:
            log.error("DatabaseRowTrigger query error: %s", e)
            return 0  # Return 0 to retry on next poll


class DeferrableDatabaseRowSensor(BaseSensorOperator):
    """
    Deferrable sensor that waits for a database row.

    Suspends the task entirely between polls (zero worker slots).
    Requires Triggerer to be running.

    Use this instead of DatabaseRowSensor when:
    - You have many sensors running simultaneously
    - You are on Kubernetes with resource-limited workers
    - Wait times exceed 30+ minutes
    """

    template_fields = ("filter_criteria", "table")
    ui_color = "#5e9de0"  # Slightly darker blue — "deferring"

    def __init__(
        self,
        conn_id: str,
        table: str,
        filter_criteria: str,
        min_row_count: int = 1,
        poke_interval: int = 300,
        **kwargs,
    ) -> None:
        # deferrable=True is set on the operator; mode is not used by deferrable sensors
        kwargs["deferrable"] = True
        super().__init__(**kwargs)
        self.conn_id = conn_id
        self.table = table
        self.filter_criteria = filter_criteria
        self.min_row_count = min_row_count
        self.poke_interval = poke_interval

    def execute(self, context: Context) -> None:
        """
        Do an immediate synchronous check, then defer if not found.
        This avoids the overhead of deferring when the condition is already met.
        """
        if self.poke(context):
            return  # Already satisfied — complete immediately

        # Not ready yet — defer to trigger
        self.defer(
            trigger=DatabaseRowTrigger(
                conn_id=self.conn_id,
                table=self.table,
                filter_criteria=self.filter_criteria,
                min_row_count=self.min_row_count,
                poll_interval=self.poke_interval,
                timeout_seconds=self.timeout,
            ),
            method_name="execute_complete",
        )

    def execute_complete(
        self,
        context: Context,
        event: dict[str, Any],
    ) -> int:
        """
        Called by Airflow when the trigger fires.

        Args:
            event: Dict from TriggerEvent containing status and row_count
        """
        if event["status"] == "timeout":
            from airflow.exceptions import AirflowSensorTimeout
            raise AirflowSensorTimeout(
                f"DatabaseRowSensor timed out after {event['elapsed_seconds']:.0f}s "
                f"waiting for rows in {self.table} WHERE {self.filter_criteria}"
            )

        row_count = event["row_count"]
        log.info(
            "Condition met: %d row(s) found in %s after %.0fs",
            row_count,
            self.table,
            event.get("elapsed_seconds", 0),
        )
        context["task_instance"].xcom_push(key="row_count", value=row_count)
        return row_count

    def poke(self, context: Context) -> bool:
        """Synchronous check — used for immediate evaluation on first execute()."""
        from airflow.hooks.dbapi import DbApiHook

        sql = f"SELECT COUNT(*) FROM {self.table} WHERE {self.filter_criteria}"
        hook = DbApiHook.get_hook(conn_id=self.conn_id)
        try:
            records = hook.get_records(sql)
            count = records[0][0] if records else 0
            log.info("Initial check: %d rows found", count)
            return count >= self.min_row_count
        except Exception as e:
            log.warning("Initial sync check failed: %s", e)
            return False
```

---

## DAG Usage

```python
# dags/orders_processing.py
from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator

from sensors.deferrable_database_row_sensor import DeferrableDatabaseRowSensor
from sensors.database_row_sensor import DatabaseRowSensor


with DAG(
    dag_id="orders_daily_processing",
    schedule="0 8 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    # Option 1: Standard sensor with reschedule mode (no Triggerer needed)
    wait_standard = DatabaseRowSensor(
        task_id="wait_for_orders_load",
        conn_id="postgres_warehouse",
        table="etl_control",
        # filter_criteria supports Jinja templates
        filter_criteria=(
            "pipeline_name = 'orders_daily' "
            "AND run_date = '{{ ds }}' "
            "AND status = 'COMPLETE'"
        ),
        poke_interval=300,      # check every 5 minutes
        timeout=3 * 3600,       # fail after 3 hours
        mode="reschedule",      # releases worker slot between pokes
    )

    # Option 2: Deferrable sensor (requires Triggerer; zero worker slots between polls)
    wait_deferrable = DeferrableDatabaseRowSensor(
        task_id="wait_for_orders_deferrable",
        conn_id="postgres_warehouse",
        table="etl_control",
        filter_criteria=(
            "pipeline_name = 'orders_daily' "
            "AND run_date = '{{ ds }}' "
            "AND status = 'COMPLETE'"
        ),
        poke_interval=300,
        timeout=3 * 3600,
    )

    process_orders = PythonOperator(
        task_id="process_orders",
        python_callable=lambda **ctx: print(
            f"Processing orders for {ctx['ds']}, "
            # Access the row_count pushed by the sensor
            f"control records: {ctx['ti'].xcom_pull('wait_for_orders_load', key='row_count')}"
        ),
    )

    wait_standard >> process_orders
```

---

## Unit Tests

```python
# tests/test_database_row_sensor.py
from unittest.mock import MagicMock, patch

import pytest

from airflow.exceptions import AirflowSensorTimeout

from sensors.database_row_sensor import DatabaseRowSensor


class TestDatabaseRowSensor:

    def _make_sensor(self, **kwargs) -> DatabaseRowSensor:
        defaults = {
            "task_id": "test_sensor",
            "conn_id": "postgres_test",
            "table": "etl_control",
            "filter_criteria": "pipeline_name = 'test' AND run_date = '2026-03-15'",
        }
        defaults.update(kwargs)
        return DatabaseRowSensor(**defaults)

    def test_default_mode_is_reschedule(self):
        sensor = self._make_sensor()
        assert sensor.mode == "reschedule"

    def test_poke_returns_true_when_row_found(self):
        sensor = self._make_sensor()
        mock_hook = MagicMock()
        mock_hook.get_records.return_value = [(1,)]

        with patch("sensors.database_row_sensor.DbApiHook") as MockDbHook:
            MockDbHook.get_hook.return_value = mock_hook
            result = sensor.poke(context={"task_instance": MagicMock()})

        assert result is True

    def test_poke_returns_false_when_no_row(self):
        sensor = self._make_sensor()
        mock_hook = MagicMock()
        mock_hook.get_records.return_value = [(0,)]

        with patch("sensors.database_row_sensor.DbApiHook") as MockDbHook:
            MockDbHook.get_hook.return_value = mock_hook
            result = sensor.poke(context={"task_instance": MagicMock()})

        assert result is False

    def test_poke_respects_min_row_count(self):
        """Sensor with min_row_count=5 returns False when only 3 rows exist."""
        sensor = self._make_sensor(min_row_count=5)
        mock_hook = MagicMock()
        mock_hook.get_records.return_value = [(3,)]

        with patch("sensors.database_row_sensor.DbApiHook") as MockDbHook:
            MockDbHook.get_hook.return_value = mock_hook
            result = sensor.poke(context={"task_instance": MagicMock()})

        assert result is False

    def test_poke_returns_false_on_query_error(self):
        """Non-connection errors return False (retry) rather than raising."""
        sensor = self._make_sensor()
        mock_hook = MagicMock()
        mock_hook.get_records.side_effect = Exception("syntax error in query")

        with patch("sensors.database_row_sensor.DbApiHook") as MockDbHook:
            MockDbHook.get_hook.return_value = mock_hook
            result = sensor.poke(context={"task_instance": MagicMock()})

        assert result is False

    def test_template_fields_include_filter_criteria(self):
        assert "filter_criteria" in DatabaseRowSensor.template_fields
        assert "table" in DatabaseRowSensor.template_fields
```
