# Forex Data Pipeline — Reference Project

This folder contains the original forex data pipeline — a real Airflow DAG that demonstrates a complete ETL workflow using HTTP sensors, file sensors, Python operators, and Bash operators.

> The fully documented version with step-by-step guide is in [`09_Capstone_Projects/01_Beginner_Projects/01_Forex_ETL_Pipeline/`](../09_Capstone_Projects/01_Beginner_Projects/01_Forex_ETL_Pipeline/).

---

## What This Pipeline Does

```
Check API → Check File → Download Rates → Save to HDFS → Create Hive Table → Process → Send Notification
```

1. **forex_data_check** — `HttpSensor` checks that the forex API is reachable
2. **forex_currencies_file_available** — `FileSensor` waits for the currencies config file
3. **downloading_rates** — `PythonOperator` calls the API and downloads exchange rates
4. **saving_rates** — `BashOperator` stores the rates to HDFS
5. **creating_forex_rates_table** — `HiveOperator` creates the target Hive table
6. **forex_processing** — `SparkSubmitOperator` processes the data
7. **send_email_notification** — `EmailOperator` sends completion notification

---

## Files

| File | Description |
|------|-------------|
| `forex-data-pipeline-v1.py` | Complete Airflow DAG |
| `api-forex-exchange.json` | Sample API response / currencies config |

---

## Key Concepts Demonstrated

- **HttpSensor** — check external API availability before running
- **FileSensor** — wait for a local file to exist
- **PythonOperator** — call Python functions as tasks
- **BashOperator** — run shell commands
- **Task dependencies** — linear pipeline with `>>` operator
- **default_args** — retries, retry_delay, owner

---

## How to Run

1. Complete [Installation & Setup](../01_Beginner/03_Installation_and_Setup/Docker_Setup.md) first.
2. Copy `forex-data-pipeline-v1.py` to your `dags/` folder.
3. Set up the required connections: `http_conn_id`, `fs_default`, `hive_conn_id`, `spark_conn_id`.
4. Trigger the DAG from the Airflow UI.

---

## 📂 Navigation

🏠 **[Home](../README.md)** &nbsp;|&nbsp; 📁 **[Full Project Guide](../09_Capstone_Projects/01_Forex_ETL_Pipeline/03_GUIDE.md)**