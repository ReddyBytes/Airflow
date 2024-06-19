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
- It is uniquely identified by the combination of a DAG, a task, and a specific execution date (`execution_date`). 
- Each Task Instance goes through various states such as `running`, `success`, `failed`, `skipped`, or `up for retry`, reflecting the outcome of the task's execution during a DAG run.

    #### Key Aspects of Task Instances

    - **Combination of DAG, Task, and Execution Date**: Defines a unique Task Instance.
    - **Execution States**: Indicates the current state of the Task Instance, such as running, successful, failed, skipped, or pending retry.
    - **Tracking and Management**: Allows for detailed tracking and management of task executions over time, facilitating debugging and monitoring of workflows.
