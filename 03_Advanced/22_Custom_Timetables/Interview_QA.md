# 22 — Custom Timetables: Interview Q&A

---

**Q1. What is a Timetable in Airflow 3 and when would you use one?**

A Timetable is a Python class that tells Airflow when to create DAG runs and what data interval (start/end time window) each run covers. Every schedule in Airflow — cron strings, `@daily`, `timedelta` objects — is implemented as a timetable internally. You write a custom timetable when the built-in schedules can't express your requirements: business days excluding holidays, last day of each month, fiscal calendar quarters, or any other custom cadence. If you can write the logic in Python, you can schedule it with a custom timetable.

---

**Q2. When should you use a custom timetable instead of a cron expression?**

Use a custom timetable when:
- You need to skip specific dates (public holidays, maintenance windows)
- Your schedule is based on calendar logic that cron can't express (last Friday of month, first business day of quarter)
- You need non-uniform intervals (e.g., different schedules for different months)
- Your fiscal calendar doesn't align with the Gregorian calendar
- You need to define custom `data_interval_start` and `data_interval_end` logic

Use a cron expression or `@daily`/`@hourly`/etc. when the schedule is uniform and regular.

---

**Q3. What is the DataInterval and what does it represent?**

A `DataInterval` represents the half-open time window `[start, end)` of data that a DAG run is responsible for processing. For a daily DAG, a run might have `start=2024-01-01` and `end=2024-01-02` — meaning it processes one day of data. The `logical_date` (formerly `execution_date`) of a DAG run equals `data_interval_start`. When you write a custom timetable, you control exactly what interval each run covers — which is especially important for reprocessing and idempotent pipelines.

---

**Q4. What methods does a custom Timetable need to implement?**

Two methods are required:

- `next_dagrun_info(last_automated_data_interval, restriction)` — called by the scheduler to determine when to create the next run. Returns a `DagRunInfo` object (containing the data interval and when to trigger the run), or `None` if there should be no next run.

- `infer_manual_data_interval(run_after)` — called when a user manually triggers a DAG. Returns a `DataInterval` representing what data period the manual run should cover.

---

**Q5. How do you register a custom timetable so Airflow can use it?**

Register it through the Airflow plugin system by creating a plugin class in the `plugins/` directory:

```python
from airflow.plugins_manager import AirflowPlugin
from my_timetables import BusinessDayTimetable

class MyPlugin(AirflowPlugin):
    name = "my_timetables_plugin"
    timetables = [BusinessDayTimetable]
```

Without registration, Airflow can't serialize and deserialize the timetable, which is required for the scheduler to persist run information in the database.

---

**Q6. How does restriction work in next_dagrun_info()?**

`TimeRestriction` contains `earliest` (the DAG's `start_date`) and `latest` (the DAG's `end_date`, if set). Your `next_dagrun_info()` implementation must respect these boundaries:
- Don't return a run earlier than `restriction.earliest`
- Return `None` if the computed next start is after `restriction.latest`

This ensures your timetable respects the DAG's start and end dates.

---

**Q7. What is the difference between CronDataIntervalTimetable and a custom Timetable?**

`CronDataIntervalTimetable` is a built-in timetable that computes run times and data intervals from a cron expression. It handles timezone-aware scheduling, DST transitions, and integrates with Airflow's catchup mechanism. A custom timetable implements the same `Timetable` interface but with arbitrary Python logic for computing the next run time. Custom timetables are more flexible but require more code. If a cron expression covers your use case, use it — custom timetables add complexity that's only justified when cron is insufficient.

---

**Q8. How do you handle timezones in a custom timetable?**

Always use `pendulum` (bundled with Airflow) for timezone-aware datetimes. Never use naive datetimes in timetables — the scheduler works in UTC internally, and naive datetimes can cause subtle bugs around DST transitions:

```python
import pendulum
tz = pendulum.timezone("America/New_York")
dt = pendulum.datetime(2024, 1, 15, 9, 0, tz=tz)
```

Store and compare all datetimes as timezone-aware. When Airflow passes datetimes to your timetable methods, they will be pendulum `DateTime` objects with timezone information.

---

## Navigation

**Prev:** [21 — Testing DAGs](../21_Testing_DAGs/Interview_QA.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [Back to Learning Path](../../00_Learning_Guide/Learning_Path.md)
