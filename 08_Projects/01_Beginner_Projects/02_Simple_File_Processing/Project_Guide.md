# 🟢 Project 02 — CSV File Processing Pipeline

> **Level:** Beginner | **Est. Time:** 1–2 hours | **Skills:** FileSensor, PythonOperator, BashOperator, XCom

---

## The Story

You're a data engineer at a logistics company. Every day around 9am, a vendor drops a CSV file of shipment records into a shared folder. Sometimes it arrives at 9:01. Sometimes 9:45. Occasionally it doesn't arrive at all.

Your job: build a pipeline that waits for the CSV to appear, validates it (is the schema correct? are there null tracking numbers?), processes the good rows, and moves the file to an archive folder. If validation fails, the file goes to a quarantine folder so the vendor can be notified.

This is the classic file-drop pipeline pattern — one of the most common workflows in data engineering.

---

## Architecture

```mermaid
flowchart LR
    subgraph Sources["Landing Zone"]
        Drop[/tmp/landing/\nshipments_YYYYMMDD.csv]
    end

    subgraph Pipeline["Airflow DAG — every 30 min, 8-11am"]
        S1[FileSensor\nwait for CSV]
        T1[PythonOperator\nread + validate CSV]
        T2{BranchPython\nall valid?}
        T3[PythonOperator\nprocess valid rows]
        T4[BashOperator\nmove to processed/]
        T5[BashOperator\nmove to quarantine/]
        T6[PythonOperator\nlog summary]
    end

    subgraph Outputs["Output Folders"]
        Proc[/tmp/processed/]
        Quar[/tmp/quarantine/]
        Log[Summary logged\nto Airflow]
    end

    Drop --> S1
    S1 --> T1
    T1 --> T2
    T2 -->|all valid| T3
    T2 -->|has errors| T5
    T3 --> T4
    T4 --> T6
    T5 --> T6
    T4 --> Proc
    T5 --> Quar
    T6 --> Log
```

---

## Prerequisites

| Requirement | Why |
|-------------|-----|
| Airflow 3 running locally | The runtime environment |
| Python `pandas` installed | CSV processing |
| No external services needed | Everything is local files |

```bash
pip install pandas
```

---

## Setup Steps

### Step 1 — Create the folder structure
```bash
mkdir -p /tmp/landing /tmp/processed /tmp/quarantine
```

### Step 2 — Create a sample CSV to test with
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

Note: TRK004 has a blank `origin` — your validation should catch this.

### Step 3 — Add the DAG and run it
```bash
cp csv_file_processing.py ~/airflow/dags/
airflow dags trigger csv_file_processing
```

---

## Expected Behaviour

**When CSV is valid:**
```
Task: wait_for_csv          → SUCCESS (file detected)
Task: validate_csv          → SUCCESS (6 columns, no critical nulls)
Task: branch_on_result      → routes to "process_valid_rows"
Task: process_valid_rows    → SUCCESS (5 rows processed)
Task: move_to_processed     → SUCCESS (file moved to /tmp/processed/)
Task: log_summary           → SUCCESS

XCom "validation_report":
{
  "file": "shipments_20240115.csv",
  "total_rows": 5,
  "valid_rows": 4,
  "invalid_rows": 1,
  "issues": [
    {"row": 4, "column": "origin", "error": "null value"}
  ]
}
```

**When CSV has critical errors (>50% bad rows):**
```
Task: branch_on_result      → routes to "quarantine_file"
Task: quarantine_file       → SUCCESS (file moved to /tmp/quarantine/)
Task: log_summary           → logs error report
```

---

## What You'll Learn

| Skill | Where it appears |
|-------|-----------------|
| FileSensor | Watching a directory for a new file |
| `mode="reschedule"` | Not blocking a worker slot while waiting |
| PythonOperator | Reading a CSV with pandas, validation logic |
| XCom | Passing the validation report between tasks |
| BranchPythonOperator | Routing to different paths based on validation result |
| BashOperator | Moving files between folders |
| `trigger_rule="none_failed_min_one_success"` | Summary task runs regardless of which branch took |

---

## Validation Checks in This Project

| Check | Logic | On Failure |
|-------|-------|-----------|
| File exists | FileSensor | Wait (up to timeout) |
| Required columns present | `set(required) ⊆ set(df.columns)` | Quarantine |
| No null tracking numbers | `df['tracking_number'].notna().all()` | Flag bad rows |
| Status values valid | `df['status'].isin(valid_statuses)` | Flag bad rows |
| Row count > 0 | `len(df) > 0` | Quarantine |
| Error rate < 50% | `bad_rows / total_rows < 0.5` | Quarantine |

---

## Extension Challenges

1. **Add schema validation** — check that `weight_kg` is numeric (not a string)
2. **Email on quarantine** — use `EmailOperator` to notify the vendor when their file fails
3. **Dead letter queue** — after 3 consecutive failures, trigger a different DAG to escalate
4. **Multi-file support** — use Dynamic Task Mapping to process multiple CSVs if they arrive simultaneously

---

## See Also

- [Code Example →](./Code_Example.md) — Complete, commented DAG code
- [Data Quality Gate →](../../02_Intermediate_Projects/03_Data_Quality_Pipeline/Project_Guide.md) — The intermediate version with S3 and 5 quality checks

---

## 📂 Navigation

| | |
|---|---|
| **Step-by-Step Guide** | [Step_by_Step.md](./Step_by_Step.md) |
| **Code Example** | [Code_Example.md](./Code_Example.md) |
| **Parent: Beginner Projects** | [01_Beginner_Projects](../Readme.md) |
| **All Projects** | [08_Projects](../../Readme.md) |
