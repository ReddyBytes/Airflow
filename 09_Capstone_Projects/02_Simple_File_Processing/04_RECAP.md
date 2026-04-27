# 04 — Recap: Simple File Processing Pipeline

---

## What You Built

A file-drop pipeline that:

1. Watches a landing folder with a `FileSensor` until the vendor's CSV arrives
2. Runs 6 automated validation checks using pandas
3. Routes the execution to either a processing path or a quarantine path based
   on the error rate, using `BranchPythonOperator`
4. Moves the file to the correct destination folder
5. Logs a unified summary regardless of which branch ran

---

## Key Concepts Reinforced

**`BranchPythonOperator`** — Airflow's mechanism for conditional execution. The
callable returns a `task_id` string and Airflow marks every other downstream branch
as "skipped". Skipped tasks do not count as failures but do block downstream tasks
that expect `all_success` (the default `trigger_rule`).

**`trigger_rule="none_failed_min_one_success"`** — the solution to the convergence
problem. When two branches re-join at a single summary task, the default
`all_success` rule would skip the summary whenever the other branch was skipped.
This trigger rule says: "run me as long as at least one upstream succeeded and
none actually failed." This is the canonical pattern for post-branch convergence.

**Error rate as the branching threshold** — instead of failing the DAG when any
bad row is found (too strict) or ignoring bad data completely (too lenient), a
threshold gives you a configurable policy. 50% is a reasonable default — below
it, quarantine the bad rows and process the good ones; above it, the whole file
is suspect.

**XCom as a report bus** — the `validation_report` dict is pushed once and pulled
by three different downstream tasks: the branch, the process task (to know which
rows to drop), and the summary (to log the report). This is XCom used well —
small structured data, multiple readers.

---

## Operators Used

| Operator | Module | What it does here |
|----------|--------|--------------------|
| `FileSensor` | `airflow.sensors.filesystem` | Polls landing dir every 30s |
| `PythonOperator` | `airflow.operators.python` | Validate, process, summarise |
| `BranchPythonOperator` | `airflow.operators.python` | Route to process or quarantine |
| `BashOperator` | `airflow.operators.bash` | Move files with `mv` |

---

## Extend It

1. **Email on quarantine** — add an `EmailOperator` as the next task after
   `quarantine_file` to notify the vendor automatically.

2. **Schema type validation** — check that `weight_kg` is actually numeric before
   calling `pd.to_numeric`. A vendor might accidentally send `"5.1 kg"` as a string.

3. **Multi-file support** — use Dynamic Task Mapping to process every CSV that
   lands in the folder within a single DAG run:
   ```python
   process.expand(file_path=landing_files)
   ```

4. **Dead letter queue** — after 3 consecutive quarantine days, trigger a
   separate "escalation" DAG that pages the vendor's data team.

5. **Write to a database** — replace the `print` stats in `process_valid_rows`
   with a `PostgresHook` insert (see Project 01 for the pattern).

---

## Files in This Project

```
02_Simple_File_Processing/
├── 01_MISSION.md       ← what/why/prerequisites
├── 02_ARCHITECTURE.md  ← DAG graph, branch logic, XCom map
├── 03_GUIDE.md         ← step-by-step guide with hints
├── src/
│   ├── starter.py      ← scaffold with TODO comments
│   └── solution.py     ← complete working DAG
└── 04_RECAP.md         ← you are here
```

---

⬅️ **Prev:** [01 — Forex ETL Pipeline](../01_Forex_ETL_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [03 — Data Quality Pipeline](../03_Data_Quality_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
