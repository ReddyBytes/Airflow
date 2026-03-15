# 22 — Custom Timetables: Cheatsheet

## Timetable Interface Methods

| Method | Called by | Must return | Purpose |
|---|---|---|---|
| `next_dagrun_info(last_automated_data_interval, restriction)` | Scheduler | `DagRunInfo` or `None` | Determine next scheduled run |
| `infer_manual_data_interval(run_after)` | Scheduler (manual trigger) | `DataInterval` | Determine interval for manual runs |

---

## DataInterval Fields

```python
from airflow.timetables.base import DataInterval
import pendulum

interval = DataInterval(
    start=pendulum.datetime(2024, 1, 1, tz="UTC"),   # inclusive
    end=pendulum.datetime(2024, 1, 2, tz="UTC"),     # exclusive
)

interval.start   # pendulum.DateTime
interval.end     # pendulum.DateTime
```

`logical_date` of a DAG run = `data_interval_start`

---

## DagRunInfo Construction

```python
from airflow.timetables.base import DagRunInfo, DataInterval

# Most common: interval-based run
info = DagRunInfo.interval(
    start=pendulum.datetime(2024, 1, 1, tz="UTC"),
    end=pendulum.datetime(2024, 1, 2, tz="UTC"),
)
# info.run_after = info.data_interval.end
# Scheduler creates the run when clock >= run_after

# Explicit run_after (run AT a specific time, covering an interval)
info = DagRunInfo.exact(moment=pendulum.datetime(2024, 1, 2, 9, 0, tz="UTC"))
```

---

## Minimal Custom Timetable Skeleton

```python
from __future__ import annotations
import pendulum
from airflow.timetables.base import (
    DagRunInfo, DataInterval, TimeRestriction, Timetable
)


class MyTimetable(Timetable):

    description = "Human-readable description shown in the UI"

    def next_dagrun_info(
        self,
        *,
        last_automated_data_interval: DataInterval | None,
        restriction: TimeRestriction,
    ) -> DagRunInfo | None:

        if last_automated_data_interval is None:
            # First run — use restriction.earliest as the starting point
            next_start = restriction.earliest
            if next_start is None:
                return None
        else:
            next_start = last_automated_data_interval.end

        next_start = self._compute_next(next_start)

        if restriction.latest is not None and next_start > restriction.latest:
            return None

        next_end = self._compute_end(next_start)
        return DagRunInfo.interval(start=next_start, end=next_end)

    def infer_manual_data_interval(self, *, run_after: pendulum.DateTime) -> DataInterval:
        start = self._compute_prev(run_after)
        end   = self._compute_next(run_after)
        return DataInterval(start=start, end=end)

    def _compute_next(self, dt: pendulum.DateTime) -> pendulum.DateTime:
        raise NotImplementedError

    def _compute_end(self, dt: pendulum.DateTime) -> pendulum.DateTime:
        raise NotImplementedError

    def _compute_prev(self, dt: pendulum.DateTime) -> pendulum.DateTime:
        raise NotImplementedError
```

---

## Plugin Registration Syntax

```python
# plugins/timetables_plugin.py
from airflow.plugins_manager import AirflowPlugin
from my_timetables.business_day import BusinessDayTimetable
from my_timetables.end_of_month import EndOfMonthTimetable


class MyTimetablesPlugin(AirflowPlugin):
    name = "my_timetables_plugin"
    timetables = [BusinessDayTimetable, EndOfMonthTimetable]
```

---

## Preset Timetable Classes

| Class | Import | Use for |
|---|---|---|
| `CronDataIntervalTimetable` | `airflow.timetables.interval` | Cron-based schedules |
| `DeltaDataIntervalTimetable` | `airflow.timetables.interval` | Fixed timedelta cadence |
| `ContinuousTimetable` | `airflow.timetables.simple` | Run as fast as possible |
| `NullTimetable` | `airflow.timetables.simple` | Manual trigger only |
| `EventListTimetable` | `airflow.timetables.events` | Run at specific datetimes |

---

## Using a Custom Timetable in a DAG

```python
from airflow import DAG
from my_timetables.business_day import BusinessDayTimetable
from datetime import datetime

with DAG(
    dag_id="my_dag",
    schedule=BusinessDayTimetable(),   # pass an instance, not the class
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:
    ...
```

---

## Navigation

**Prev:** [21 — Testing DAGs](../21_Testing_DAGs/Cheatsheet.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [Back to Learning Path](../../00_Learning_Guide/Learning_Path.md)
