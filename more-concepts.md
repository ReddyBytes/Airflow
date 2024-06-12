### Start Date

The **Start Date** refers to the moment when a task or a DAG (Directed Acyclic Graph) begins its execution cycle.

### Schedule Interval

The **Schedule Interval** defines how often a task or a DAG should run. It is expressed in terms of cron syntax.

### Execution Date

The **Execution Date** represents the actual date when a task instance was executed.

![](https://miro.medium.com/v2/resize:fit:1400/1*HtxgPgOIFxR3uhfkxePqOg.png)  

### Catchup
- Automatically schedules and executes all missed DAG runs from `start_date` to now.
- Enabled by default (`catchup=True`).
- Can overload system resources if `start_date` is far in the past and `schedule_interval` is frequent.

### Backfill
- Manually selects a range of past dates to execute the DAG.
- Performed via CLI with `airflow dags backfill`.
- Allows for targeted historical data processing.