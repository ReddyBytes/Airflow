# 02 — Architecture: Simple File Processing Pipeline

---

## DAG Task Graph

This pipeline splits into two branches after validation. Only one branch runs
per execution — then both converge at `log_summary`.

```
wait_for_csv
     │
     ▼
validate_csv
     │
     ▼
branch_on_result
     │
     ├─── error_rate < 50% ────► process_valid_rows ──► move_to_processed ──┐
     │                                                                        │
     └─── error_rate >= 50% ───► quarantine_file ────────────────────────────┤
                                                                              │
                                                                              ▼
                                                                         log_summary
                                                              (trigger_rule=none_failed_min_one_success)
```

The `log_summary` task uses `trigger_rule="none_failed_min_one_success"` — it
runs as long as at least one of its upstream tasks succeeded and none failed
unexpectedly. Without this, Airflow would skip it when the branch task marks
the unselected path as "skipped".

---

## Data Flow

```
/tmp/landing/
shipments_YYYYMMDD.csv
       │
       │  FileSensor detects file
       ▼
  validate_csv
  ┌─────────────────────────────────────┐
  │ pandas.read_csv()                   │
  │ Check 1: required columns present   │
  │ Check 2: no null tracking numbers   │
  │ Check 3: no null origins            │
  │ Check 4: valid status values        │
  │ Check 5: positive weight_kg         │
  │ Calculate: bad_rows / total_rows    │
  └─────────────────────────────────────┘
       │
       │ XCom push: "validation_report" dict
       │ XCom push: "csv_path" string
       ▼
  branch_on_result
  (reads validation_report["passed"])
       │
  True │                          False │
       ▼                                ▼
  process_valid_rows          quarantine_file
  (filter + process)          (mv → /tmp/quarantine/)
       │
       ▼
  move_to_processed
  (mv → /tmp/processed/)
       │
       └────────────────────────► log_summary
```

---

## Branch Logic

```python
if report["error_rate"] < MAX_ERROR_RATE:   # MAX_ERROR_RATE = 0.50
    return "process_valid_rows"
else:
    return "quarantine_file"
```

A `BranchPythonOperator` callable must return the `task_id` (as a string) of
the next task to execute. Airflow marks all other downstream tasks as "skipped".

---

## XCom Map

| Producer task | XCom key | Consumer task |
|---|---|---|
| `validate_csv` | `validation_report` | `branch_on_result`, `process_valid_rows`, `log_summary` |
| `validate_csv` | `csv_path` | `quarantine_file`, `move_to_processed` |
| `process_valid_rows` | `rows_processed` | `log_summary` |

---

## File System Layout

```
/tmp/
├── landing/
│   └── shipments_YYYYMMDD.csv    ← vendor drops files here
├── processed/
│   └── shipments_YYYYMMDD.csv    ← moved here after successful processing
└── quarantine/
    └── shipments_YYYYMMDD.csv    ← moved here when error rate ≥ 50%
```

The original file is always moved out of `landing/` — either to `processed/`
or `quarantine/`. The landing folder is never left with stale files.

---

## Tech Stack

| Component | Role |
|-----------|------|
| Airflow 3 (DAG SDK) | Orchestration |
| `FileSensor` (core) | Wait for CSV drop |
| `BranchPythonOperator` | Route on validation result |
| `pandas` | CSV reading and validation logic |
| `BashOperator` | Move files between directories |
| Local filesystem | No external services required |

---

## DAG Schedule

```
schedule="*/30 8-11 * * 1-5"
```

Breakdown: every 30 minutes (`*/30`), between hours 8 and 11 (`8-11`),
Monday to Friday (`1-5`). The FileSensor inside the DAG will wait up to
2 hours for the file — the DAG simply keeps triggering every 30 minutes
and the sensor pokes until it finds the file.

---

⬅️ **Prev:** [01 — Mission](./01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [03 — Guide](./03_GUIDE.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
