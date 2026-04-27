# 04 — Recap: Forex ETL Pipeline

---

## What You Built

A production-grade daily ETL pipeline that:

1. Guards the run with two sensors — no data fetched until the API and config file are confirmed ready
2. Pulls live forex rates from a public REST API using `HttpHook`
3. Transforms the JSON response into a flat CSV using Python's built-in `csv` module
4. Persists rates to PostgreSQL with a schema designed for idempotency
5. Emails a summary to stakeholders and cleans up temp files

---

## Key Concepts Reinforced

**Sensors as guards** — `HttpSensor` and `FileSensor` let the pipeline wait for
external dependencies instead of failing immediately. Setting `mode="reschedule"`
on a sensor that might wait minutes (not seconds) is a critical production habit —
it returns the worker slot to the pool rather than blocking it.

**XCom as the data bus** — tasks don't share memory or files directly. XCom is the
formal channel: producer tasks push with `ti.xcom_push`, consumer tasks pull with
`ti.xcom_pull`. Keeping XCom values small (dicts, strings, numbers) is best practice
— large DataFrames belong on disk or in object storage.

**Idempotency by design** — `CREATE TABLE IF NOT EXISTS` and `ON CONFLICT DO NOTHING`
mean you can re-trigger any failed run without cleaning up first. This is the single
most important property for scheduled pipelines.

**`trigger_rule="all_done"`** — cleanup tasks should run even when upstream tasks
fail. Default `trigger_rule` is `"all_success"`, which means cleanup would be skipped
on failure and leave orphaned files. Always use `"all_done"` for teardown tasks.

---

## Operators Used

| Operator | Module | What it does here |
|----------|--------|--------------------|
| `HttpSensor` | `providers.http.sensors.http` | Polls API until 200 response |
| `FileSensor` | `airflow.sensors.filesystem` | Waits for config file |
| `PythonOperator` | `airflow.operators.python` | Fetch, transform, load, notify |
| `PostgresOperator` | `providers.postgres.operators.postgres` | Runs CREATE TABLE SQL |
| `BashOperator` | `airflow.operators.bash` | Deletes temp CSV |

---

## Extend It

1. **Add retries** — set `retries=3, retry_delay=timedelta(minutes=5)` on the
   `fetch_rates` task to handle transient API failures automatically.

2. **Real email** — replace the `print` in `send_summary_email` with:
   ```python
   from airflow.utils.email import send_email
   send_email(to="risk-team@company.com", subject=subject, html_content=body)
   ```

3. **Historical backfill** — set `catchup=True` on the DAG and run:
   ```bash
   airflow dags backfill forex_etl_pipeline --start-date 2024-01-01 --end-date 2024-01-31
   ```
   Because the inserts are idempotent, re-running any date is safe.

4. **Add a ShortCircuitOperator** — skip the run if rates for today were already
   loaded (query the table, return `False` if rows exist).

5. **Parameterise the base currency** — use `Variable.get("forex_base_currency", default_var="USD")`
   so you can change the base without editing the DAG code.

---

## Files in This Project

```
01_Forex_ETL_Pipeline/
├── 01_MISSION.md       ← what/why/prerequisites
├── 02_ARCHITECTURE.md  ← DAG graph, data flow, tech stack
├── 03_GUIDE.md         ← this step-by-step guide
├── src/
│   ├── starter.py      ← scaffold with TODO comments
│   └── solution.py     ← complete working DAG
└── 04_RECAP.md         ← you are here
```

---

➡️ **Next:** [02 — Simple File Processing](../02_Simple_File_Processing/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
