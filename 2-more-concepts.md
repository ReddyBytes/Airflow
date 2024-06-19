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

Trigger rules define under what conditions a task should be executed relative to its upstream task

#### Key Trigger Rules

- **`all_success`**: The default rule. A task is triggered only if all its upstream tasks have succeeded.
- **`all_failed`**: A task is triggered if all its upstream tasks have failed.
- **`all_done`**: A task is triggered if all its upstream tasks have either succeeded or failed.
- **`one_success`**: A task is triggered if at least one of its upstream tasks has succeeded.
- **`one_failed`**: A task is triggered if at least one of its upstream tasks has failed.
- **`none_failed`**: A task is triggered if none of its upstream tasks have failed.
- **`none_skipped`**: A task is triggered if none of its upstream tasks have been skipped.
- **`dummy`**: A task is always triggered, regardless of the states of its upstream tasks.

## Hard Coding in Airflow

Hard coding refers to embedding static values directly into your DAGs or task definitions, rather than dynamically fetching or calculating those values at runtime. 
  
    file_path = "/home/user/data.csv"
    schedule_interval='@daily'

`we can avoid hard coding by using variables,templates and Macros`

### 1)  Variables 

- Variables serve as a key-value store that can be used to store information globally within your Airflow environment. 
- They are particularly useful for storing configuration settings, secrets, or any other data that needs to be accessed across different tasks or DAGs.

    #### Creating Variables

    1. Navigate to the **Admin** tab in the Airflow UI.
    2. Select **Variables**.
    3. Click on the **+** button to add a new variable.
    4. Enter a key, value, and an optional description for your variable.

### 2) Templating in Apache Airflow

- Templating in Airflow leverages Jinja templating, allowing you to dynamically insert values into your DAGs and tasks. 
- Templating in Airflow uses Jinja's double curly braces `{{ }}` to denote placeholders for dynamic content. 

    #### Commonly Used Variables

    - `{{ ds }}`: The DAG Run’s logical date as YYYY-MM-DD.
    - `{{ ds_nodash }}`: The DAG run’s logical date as YYYYMMDD.
    - `{{ data_interval_start }}`: The start of the data interval.
    - `{{ data_interval_end }}`: The end of the data interval.

### 3) Macros 

- Macros are predefined variables and functions that can be used within your DAG definitions. 
- They facilitate dynamic programming and promote code reusability. 
- Macros are particularly useful for injecting runtime information into your tasks, such as the DAG run's execution date or the next scheduled run time.

    #### Built-In Macros

    - `{{ ds }}`: The DAG run’s logical date as YYYY-MM-DD.
    - `{{ dag }}`: Represents the current DAG object, allowing access to its attributes such as ID, description, or schedule interval.
    - `{{ prev_ds }}`: Indicates the previous execution date of the DAG in the format `YYYY-MM-DD`.
    - `{{ next_ds }}`: Shows the next scheduled execution date of the DAG in the format `YYYY-MM-DD`.
    - `{{ ds_nodash }}`: The DAG run’s logical date as YYYYMMDD.
    - `{{ data_interval_start }}`: The start of the data interval.
    - `{{ data_interval_end }}`: The end of the data interval.
    - `{{ execution_date }}`: The execution date of the DAG run.
    - `{{ ts }}`: The timestamp of the DAG run.
    - `{{ prev_execution_date }}`: The last successful execution date of the DAG.

for more built in macros [see here](https://airflow.apache.org/docs/apache-airflow/1.10.5/macros.html)

