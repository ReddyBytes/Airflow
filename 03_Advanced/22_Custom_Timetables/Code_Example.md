# 22 — Custom Timetables: Code Examples

---

## Example 1: Business Days Timetable (Skip Weekends)

A timetable that schedules one run per business day (Monday–Friday), skipping Saturday and Sunday. Each run covers one calendar day.

```python
# dags/timetables/business_day.py
from __future__ import annotations

import pendulum
from pendulum import DateTime, Duration

from airflow.timetables.base import (
    DagRunInfo,
    DataInterval,
    TimeRestriction,
    Timetable,
)


class BusinessDayTimetable(Timetable):
    """
    Schedules one run per business day (Mon–Fri).
    Each run covers exactly one calendar day:
      data_interval_start = 00:00:00 on that business day
      data_interval_end   = 00:00:00 on the next day
    Weekends are skipped entirely.
    """

    description = "Once per business day (Monday–Friday)"

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _next_business_day(dt: DateTime) -> DateTime:
        """Return the next day that is a weekday (Mon=0 … Fri=4)."""
        candidate = dt.add(days=1).start_of("day")
        while candidate.day_of_week >= 5:   # 5=Saturday, 6=Sunday
            candidate = candidate.add(days=1)
        return candidate

    @staticmethod
    def _current_or_next_business_day(dt: DateTime) -> DateTime:
        """
        If dt falls on a weekday, return start of that day.
        If dt falls on a weekend, advance to the next Monday.
        """
        candidate = dt.start_of("day")
        while candidate.day_of_week >= 5:
            candidate = candidate.add(days=1)
        return candidate

    # ── Timetable interface ───────────────────────────────────────────────────

    def next_dagrun_info(
        self,
        *,
        last_automated_data_interval: DataInterval | None,
        restriction: TimeRestriction,
    ) -> DagRunInfo | None:

        if last_automated_data_interval is None:
            # First run: start from the DAG's start_date
            if restriction.earliest is None:
                return None
            next_start = self._current_or_next_business_day(restriction.earliest)
        else:
            # Subsequent runs: start from the day after the last interval ended
            next_start = self._next_business_day(last_automated_data_interval.end)

        # Respect the DAG's end_date
        if restriction.latest is not None and next_start > restriction.latest:
            return None

        next_end = next_start.add(days=1)

        return DagRunInfo.interval(start=next_start, end=next_end)

    def infer_manual_data_interval(self, *, run_after: DateTime) -> DataInterval:
        """
        For manual triggers: cover the business day that contains run_after.
        If run_after is on a weekend, cover the previous Friday.
        """
        # Walk backward to the most recent weekday
        candidate = run_after.start_of("day")
        while candidate.day_of_week >= 5:
            candidate = candidate.subtract(days=1)

        return DataInterval(
            start=candidate,
            end=candidate.add(days=1),
        )


# ── Plugin registration ───────────────────────────────────────────────────────

# plugins/timetables_plugin.py
from airflow.plugins_manager import AirflowPlugin
from dags.timetables.business_day import BusinessDayTimetable


class TimetablesPlugin(AirflowPlugin):
    name = "custom_timetables_plugin"
    timetables = [BusinessDayTimetable]
```

### Using BusinessDayTimetable in a DAG

```python
# dags/daily_business_report.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from dags.timetables.business_day import BusinessDayTimetable
import pendulum
import logging


def generate_report(**context):
    start = context["data_interval_start"]
    end   = context["data_interval_end"]
    logging.info(
        f"Generating business day report for: "
        f"{start.date()} → {end.date()}"
    )
    logging.info(
        f"Day of week: {start.day_of_week} "
        f"({start.format('dddd')})"
    )
    # Verify it's a weekday (sanity check)
    assert start.day_of_week < 5, f"Unexpected weekend run: {start}"


with DAG(
    dag_id="daily_business_report",
    description="Generates a daily report on business days only",
    schedule=BusinessDayTimetable(),
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["reports", "business-day"],
) as dag:

    report_task = PythonOperator(
        task_id="generate_report",
        python_callable=generate_report,
    )
```

**What you'll see in the UI:**
- The DAG runs Monday through Friday
- Saturday and Sunday have no scheduled runs
- Each run's `data_interval_start` is midnight on that weekday
- `data_interval_end` is midnight the following day

---

## Example 2: End-of-Month Timetable

A timetable that schedules one run on the last day of each month. Each run covers the entire preceding month (from the 1st to the last day).

```python
# dags/timetables/end_of_month.py
from __future__ import annotations

import pendulum
from pendulum import DateTime

from airflow.timetables.base import (
    DagRunInfo,
    DataInterval,
    TimeRestriction,
    Timetable,
)


class EndOfMonthTimetable(Timetable):
    """
    Schedules one run on the last day of each month.
    Each run covers the full calendar month:
      data_interval_start = first day of that month (00:00:00)
      data_interval_end   = first day of the following month (00:00:00)

    Run is triggered at the END of the month (data_interval.end = run trigger).
    """

    description = "Once per month, on the last day of the month"

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _month_start(dt: DateTime) -> DateTime:
        """Return the first moment of the month containing dt."""
        return dt.start_of("month")

    @staticmethod
    def _next_month_start(dt: DateTime) -> DateTime:
        """Return the first moment of the month following dt's month."""
        return dt.start_of("month").add(months=1)

    @staticmethod
    def _last_day_of_month(dt: DateTime) -> DateTime:
        """Return midnight on the last day of dt's month."""
        return dt.end_of("month").start_of("day")

    # ── Timetable interface ───────────────────────────────────────────────────

    def next_dagrun_info(
        self,
        *,
        last_automated_data_interval: DataInterval | None,
        restriction: TimeRestriction,
    ) -> DagRunInfo | None:

        if last_automated_data_interval is None:
            # First run: cover the month containing the DAG's start_date
            if restriction.earliest is None:
                return None
            start = self._month_start(restriction.earliest)
        else:
            # Subsequent runs: cover the next month
            start = last_automated_data_interval.end

        end = self._next_month_start(start)

        # The run is triggered on the last day of the month (= day before end)
        run_trigger_day = self._last_day_of_month(start)

        # Respect the DAG's end_date
        if restriction.latest is not None and run_trigger_day > restriction.latest:
            return None

        return DagRunInfo(
            run_after=run_trigger_day,
            data_interval=DataInterval(start=start, end=end),
        )

    def infer_manual_data_interval(self, *, run_after: DateTime) -> DataInterval:
        """
        For manual triggers: cover the calendar month that contains run_after.
        """
        start = self._month_start(run_after)
        end   = self._next_month_start(run_after)
        return DataInterval(start=start, end=end)


# ── Plugin registration (add to plugins/timetables_plugin.py) ────────────────

# from dags.timetables.end_of_month import EndOfMonthTimetable
#
# class TimetablesPlugin(AirflowPlugin):
#     name = "custom_timetables_plugin"
#     timetables = [BusinessDayTimetable, EndOfMonthTimetable]
```

### Using EndOfMonthTimetable in a DAG

```python
# dags/monthly_summary.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from dags.timetables.end_of_month import EndOfMonthTimetable
import pendulum
import logging


def generate_monthly_summary(**context):
    start = context["data_interval_start"]
    end   = context["data_interval_end"]
    year  = start.year
    month = start.month

    logging.info(f"Generating monthly summary for: {year}-{month:02d}")
    logging.info(f"Data interval: {start.date()} → {end.date()}")
    logging.info(f"Days in period: {(end - start).days}")

    # Verify we're covering a full month
    assert start.day == 1, f"Interval should start on day 1, got day {start.day}"
    assert end.day == 1, f"Interval should end on day 1 of next month, got day {end.day}"
    assert end.month == (month % 12) + 1 or (end.year == year + 1 and end.month == 1), \
        "Interval should span exactly one calendar month"


def send_report_email(**context):
    start = context["data_interval_start"]
    logging.info(
        f"Sending monthly report email for "
        f"{start.format('MMMM YYYY')} to stakeholders..."
    )


with DAG(
    dag_id="monthly_summary_report",
    description="Generates a summary report on the last day of each month",
    schedule=EndOfMonthTimetable(),
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    tags=["reports", "monthly"],
) as dag:

    summarize = PythonOperator(
        task_id="generate_monthly_summary",
        python_callable=generate_monthly_summary,
    )

    email = PythonOperator(
        task_id="send_report_email",
        python_callable=send_report_email,
    )

    summarize >> email
```

**What you'll see in the UI:**
- January run: triggered on Jan 31st, `data_interval_start=Jan 1`, `data_interval_end=Feb 1`
- February run: triggered on Feb 28/29th (last day of February), covers all of February
- March run: triggered on Mar 31st, covers all of March
- Each run's `logical_date` = first day of the month it covers

---

## Navigation

**Prev:** [21 — Testing DAGs](../21_Testing_DAGs/Code_Example.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [Back to Learning Path](../../00_Learning_Guide/Learning_Path.md)
