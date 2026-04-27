# 03 — Step-by-Step Guide: Simple File Processing Pipeline

This guide is partially guided — key patterns are shown, but some implementation
decisions are left for you to work out. Use the hint blocks when you're stuck.

---

## Step 1 — Set Up Folders and Test Data

```bash
mkdir -p /tmp/landing /tmp/processed /tmp/quarantine

# Create the happy-path test file
cat > /tmp/landing/shipments_$(date +%Y%m%d).csv << 'EOF'
tracking_number,origin,destination,weight_kg,status
TRK001,New York,Los Angeles,12.5,in_transit
TRK002,Chicago,Miami,3.2,delivered
TRK003,Seattle,Boston,8.9,pending
TRK004,,Dallas,5.1,in_transit
TRK005,Atlanta,Denver,2.0,delivered
EOF
```

Configure the `fs_default` connection so `FileSensor` can access the filesystem:
1. Airflow UI → Admin → Connections → `+`
2. Conn ID: `fs_default`, Conn Type: `File (path)`, Extra: `{"path": "/"}`
3. Save.

---

## Step 2 — Build the FileSensor

The sensor must watch the landing directory for a file matching
`shipments_*.csv`. It runs every 30 seconds and gives up after 2 hours
(the window when the vendor should deliver).

<details>
<summary>💡 Hint — FileSensor parameters</summary>

Key parameters:
- `filepath` — glob or exact path. Use `"/tmp/landing/shipments_*.csv"` for a wildcard.
- `fs_conn_id="fs_default"` — the connection you just configured.
- `mode="reschedule"` — mandatory for anything that might wait more than a few seconds.
- `timeout=7200` — 2 hours in seconds.

</details>

<details>
<summary>✅ Answer</summary>

```python
wait_for_csv = FileSensor(
    task_id="wait_for_csv",
    filepath=f"{LANDING_DIR}/shipments_*.csv",
    fs_conn_id="fs_default",
    poke_interval=30,
    timeout=7200,
    mode="reschedule",
)
```

</details>

---

## Step 3 — Build the Validation Task

This is the core of the pipeline. Write a `validate_csv` callable that:

1. Finds the CSV file in the landing directory (use `glob.glob`)
2. Loads it with `pandas.read_csv()`
3. Runs the 6 checks listed in `01_MISSION.md`
4. Builds a `validation_report` dict with keys: `file`, `csv_path`, `total_rows`,
   `valid_rows`, `invalid_rows`, `error_rate`, `issues`, `passed`
5. Pushes `validation_report` and `csv_path` to XCom

<details>
<summary>💡 Hint — collecting issues</summary>

Build an `issues` list. Each check appends dicts to it when it finds a problem:
```python
issues = []

null_tracking = df[df["tracking_number"].isna()]
for idx, row in null_tracking.iterrows():
    issues.append({
        "row": int(idx) + 2,           # +2 = 1-index + header row
        "column": "tracking_number",
        "error": "null value — required field",
    })
```

Then calculate `error_rate`:
```python
bad_row_numbers = {issue["row"] for issue in issues if isinstance(issue["row"], int)}
error_rate = len(bad_row_numbers) / total_rows
passed = error_rate < MAX_ERROR_RATE   # MAX_ERROR_RATE = 0.50
```

</details>

<details>
<summary>✅ Answer — validate_csv callable (abridged)</summary>

```python
def validate_csv(**context):
    import glob

    files = sorted(glob.glob(f"{LANDING_DIR}/shipments_*.csv"))
    if not files:
        raise FileNotFoundError(f"No shipments CSV in {LANDING_DIR}")

    csv_path = max(files, key=os.path.getmtime)
    df = pd.read_csv(csv_path)
    total_rows = len(df)

    if total_rows == 0:
        raise ValueError("CSV is empty")

    missing_cols = REQUIRED_COLUMNS - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing columns: {missing_cols}")

    issues = []

    for idx, row in df[df["tracking_number"].isna()].iterrows():
        issues.append({"row": int(idx)+2, "column": "tracking_number", "error": "null"})

    for idx, row in df[df["origin"].isna()].iterrows():
        issues.append({"row": int(idx)+2, "column": "origin", "error": "null"})

    for idx, row in df[~df["status"].isin(VALID_STATUSES)].iterrows():
        issues.append({"row": int(idx)+2, "column": "status",
                       "error": f"invalid: {row['status']}"})

    df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="coerce")
    for idx, row in df[df["weight_kg"] <= 0].iterrows():
        issues.append({"row": int(idx)+2, "column": "weight_kg",
                       "error": f"non-positive: {row['weight_kg']}"})

    bad_rows = {i["row"] for i in issues if isinstance(i["row"], int)}
    error_rate = len(bad_rows) / total_rows

    report = {
        "file": Path(csv_path).name,
        "csv_path": csv_path,
        "total_rows": total_rows,
        "valid_rows": total_rows - len(bad_rows),
        "invalid_rows": len(bad_rows),
        "error_rate": round(error_rate, 4),
        "issues": issues,
        "passed": error_rate < MAX_ERROR_RATE,
    }

    context["ti"].xcom_push(key="validation_report", value=report)
    context["ti"].xcom_push(key="csv_path", value=csv_path)
    return report
```

</details>

---

## Step 4 — Build the Branch Task

The `BranchPythonOperator` callable reads the validation report and returns
the `task_id` of the next task to run.

<details>
<summary>💡 Hint — BranchPythonOperator return value</summary>

The callable must return a string (or list of strings) matching a downstream
`task_id`. Airflow marks all other downstream tasks as "skipped".

```python
def decide_route(**context) -> str:
    report = context["ti"].xcom_pull(task_ids="validate_csv", key="validation_report")
    return "process_valid_rows" if report["passed"] else "quarantine_file"

branch = BranchPythonOperator(
    task_id="branch_on_result",
    python_callable=decide_route,
)
```

</details>

---

## Step 5 — Build the Two Branch Tasks

**Process path:** filter the DataFrame to valid rows (drop the bad row indices from the issues list), print stats.

**Quarantine path:** use a `BashOperator` to `mv` the file to `/tmp/quarantine/`.

<details>
<summary>💡 Hint — getting bad row indices from the report</summary>

```python
report = context["ti"].xcom_pull(task_ids="validate_csv", key="validation_report")
bad_indices = {issue["row"] - 2 for issue in report["issues"]
               if isinstance(issue["row"], int)}
valid_df = df.drop(index=list(bad_indices), errors="ignore")
```

</details>

---

## Step 6 — Wire Dependencies and Set the Summary trigger_rule

Connect the tasks. The key challenge: `log_summary` must run after either branch.

<details>
<summary>💡 Hint — trigger_rule for the convergence task</summary>

Set `trigger_rule="none_failed_min_one_success"` on `log_summary`.
Without it, Airflow sees "skipped" upstream tasks and also skips `log_summary`.

```python
summary = PythonOperator(
    task_id="log_summary",
    python_callable=log_summary,
    trigger_rule="none_failed_min_one_success",
)
```

Dependency wiring:
```python
wait_for_csv >> validate >> branch
branch >> process >> move_to_processed >> summary
branch >> quarantine >> summary
```

</details>

---

## Test Commands

```bash
# Trigger the DAG
airflow dags trigger csv_file_processing

# Check what's in each folder after the run
ls /tmp/processed/   # should have the CSV (happy path)
ls /tmp/quarantine/  # should be empty

# Test the quarantine path — create a file with 3 out of 5 bad rows
cat > /tmp/landing/shipments_$(date +%Y%m%d).csv << 'EOF'
tracking_number,origin,destination,weight_kg,status
TRK001,New York,LA,12.5,in_transit
,Chicago,Miami,3.2,delivered
,Seattle,Boston,8.9,pending
,Dallas,Houston,5.1,in_transit
TRK005,Atlanta,Denver,2.0,delivered
EOF
# 60% error rate → should route to quarantine
```

---

⬅️ **Prev:** [02 — Architecture](./02_ARCHITECTURE.md) &nbsp;&nbsp; ➡️ **Next:** [04 — Recap](./04_RECAP.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
