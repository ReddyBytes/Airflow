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


### Trigger Rules 

- Trigger rules define under what conditions a task should be executed relative to its upstream task  

    #### Key Trigger Rules

    - **`all_success`**: The default rule. A task is triggered only if all its upstream tasks have succeeded.
    - **`all_failed`**: A task is triggered if all its upstream tasks have failed.
    - **`all_done`**: A task is triggered if all its upstream tasks have either succeeded or failed.
    - **`one_success`**: A task is triggered if at least one of its upstream tasks has succeeded.
    - **`one_failed`**: A task is triggered if at least one of its upstream tasks has failed.
    - **`none_failed`**: A task is triggered if none of its upstream tasks have failed.
    - **`none_skipped`**: A task is triggered if none of its upstream tasks have been skipped.
    - **`dummy`**: A task is always triggered, regardless of the states of its upstream tasks.


### Task Instances 

- A Task Instance represents a specific execution of a task within a DAG.

- Each task defined in a DAG can have multiple Task Instances, each corresponding to a different execution of the task

- Each Task Instance goes through various states such as `running`, `success`, `failed`, `skipped`, or `up for retry`, reflecting the outcome of the task's execution during a DAG run.



### Dag Run

- A DAGRun represents a single execution of a DAG. 

- When a DAG is scheduled to run, Airflow creates a DAGRun for that execution. Each DAGRun contains multiple Task Instances, one for each task defined in the DAG.

- The DAGRun tracks the overall progress of the DAG, including the completion status of all tasks within the DAG.


### Ad Hoc Queries 

- Ad Hoc Queries allows users to interactively perform SQL queries against the Airflow metadata database. 
- his feature was part of the Data Profiling tools available in Airflow versions prior to 2.0.0.



