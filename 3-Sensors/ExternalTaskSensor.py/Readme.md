## ExternalTaskSensor in Apache Airflow

- The `ExternalTaskSensor` is designed to pause the execution of a task until a specified external task completes successfully.  
-  This sensor is particularly useful in scenarios where the execution of one DAG depends on the successful completion of another DAG or task. 


### How It Works

- **Waiting for Completion**: The sensor continuously polls the status of the specified external task. Once the external task succeeds, the sensor also marks itself as succeeded, allowing the dependent task to proceed.

- **Timeout and Retry Logic**: The sensor includes mechanisms for handling timeouts and retries, ensuring robustness against transient failures in the external task.

### Configuration Options

- **`external_task_id`**: Specifies the ID of the external task to wait for. This can be a task within another DAG.

- **`external_task_group_id`**: Optionally, specifies the ID of an external task group. If both `external_task_id` and `external_task_group_id` are set, the sensor waits for a task within the specified task group.

- **`mode`**: Determines the sensor's behavior upon the external task's failure. The default mode is `reschedule`, which reschedules the sensor after a delay. Other modes include `ignore_all_errors` and `ignore_failed`.

- **`poke_interval`**: Controls how often the sensor pokes the external task to check its status. The default value is 300 seconds (5 minutes).
