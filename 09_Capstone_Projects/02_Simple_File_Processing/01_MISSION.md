# 01 — Simple File Processing Pipeline

## 🟡 Partially Guided

> **Difficulty:** Beginner+ &nbsp;|&nbsp; **Est. Time:** 1–2 hours &nbsp;|&nbsp; **Airflow version:** 3.x

---

## The Story

You're a data engineer at a logistics company. Every morning around 9am a vendor
drops a CSV file of shipment records into a shared folder. Sometimes it arrives at
9:01. Sometimes 9:45. Occasionally it doesn't arrive at all.

Your job: build a pipeline that waits for the CSV to appear, validates the data
(correct schema? no null tracking numbers? valid status values?), processes the
good rows, and moves the file to an archive folder. If too many rows are bad, the
file goes to a quarantine folder so the vendor can be notified.

This is the **file-drop pipeline** pattern — one of the most common workflows in
data engineering.

---

## What You'll Build

A DAG that runs every 30 minutes between 8am and 11am on weekdays:

| # | Task | Operator | Description |
|---|------|----------|-------------|
| 1 | `wait_for_csv` | FileSensor | Watch the landing folder for the daily CSV |
| 2 | `validate_csv` | PythonOperator | Read the file, run 5 validation checks, push report to XCom |
| 3 | `branch_on_result` | BranchPythonOperator | Route to process or quarantine based on error rate |
| 4a | `process_valid_rows` | PythonOperator | Filter to valid rows and process them |
| 4b | `quarantine_file` | BashOperator | Move bad file to /tmp/quarantine/ |
| 5a | `move_to_processed` | BashOperator | Archive the processed file |
| 6 | `log_summary` | PythonOperator | Print a run summary (runs after either branch) |

---

## Skills You'll Practice

- **FileSensor** with `mode="reschedule"` — polling a directory without blocking workers
- **PythonOperator** with pandas — reading and validating CSV content
- **XCom** — passing a validation report dict between tasks
- **BranchPythonOperator** — routing the DAG to different paths based on data quality
- **BashOperator** — moving files between directories
- **`trigger_rule="none_failed_min_one_success"`** — running a summary task after either branch

---

## Prerequisites

| Requirement | Why |
|-------------|-----|
| Airflow 3 running locally | Runtime |
| `pandas` installed | CSV processing |
| No external services | Everything is local files |

```bash
pip install pandas
```

**Create the folder structure:**
```bash
mkdir -p /tmp/landing /tmp/processed /tmp/quarantine
```

**Create a sample file to test with:**
```bash
cat > /tmp/landing/shipments_$(date +%Y%m%d).csv << 'EOF'
tracking_number,origin,destination,weight_kg,status
TRK001,New York,Los Angeles,12.5,in_transit
TRK002,Chicago,Miami,3.2,delivered
TRK003,Seattle,Boston,8.9,pending
TRK004,,Dallas,5.1,in_transit
TRK005,Atlanta,Denver,2.0,delivered
EOF
```

Note: TRK004 has a blank `origin` — your validation should flag this but not quarantine the file (only 1 out of 5 = 20% error rate, below the 50% threshold).

---

## Validation Checks

| Check | Logic | On Failure |
|-------|-------|-----------|
| Required columns present | `set(required) ⊆ set(df.columns)` | Raise immediately |
| Row count > 0 | `len(df) > 0` | Raise immediately |
| No null tracking numbers | `df['tracking_number'].notna()` | Flag bad rows |
| No null origins | `df['origin'].notna()` | Flag bad rows |
| Valid status values | `df['status'].isin(VALID_STATUSES)` | Flag bad rows |
| Positive weight | `df['weight_kg'] > 0` | Flag bad rows |
| Error rate < 50% | `bad_rows / total_rows < 0.50` | Quarantine whole file |

---

## Expected Behaviour

**Happy path (error rate < 50%):**
```
wait_for_csv         → SUCCESS
validate_csv         → SUCCESS (valid_rows=4, invalid_rows=1, error_rate=20%)
branch_on_result     → routes to process_valid_rows
process_valid_rows   → SUCCESS
move_to_processed    → SUCCESS
log_summary          → SUCCESS
```

**Quarantine path (error rate ≥ 50%):**
```
branch_on_result     → routes to quarantine_file
quarantine_file      → SUCCESS
log_summary          → SUCCESS (logs error details)
```

---

## Difficulty Badge

**🟡 Partially Guided** — the starter file has task definitions with TODO comments
pointing you to the right patterns, but you need to figure out some of the details
yourself. The hints in `03_GUIDE.md` are there if you get stuck.

---

⬅️ **Prev:** [01 — Forex ETL Pipeline](../01_Forex_ETL_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [03 — Data Quality Pipeline](../03_Data_Quality_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
