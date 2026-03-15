# Airflow + Apache Spark — Interview Q&A

These questions come up in data engineering interviews where Spark is the compute
layer and Airflow is the orchestrator.

---

## Q1. How does Airflow integrate with Apache Spark?

**Answer:**
Airflow does not run Spark itself — it **submits** Spark jobs and monitors their
completion. The integration happens through:

1. **SparkSubmitOperator**: calls `spark-submit` on the Airflow worker machine.
   Requires the Spark client binaries to be installed on the worker.

2. **LivyOperator**: sends HTTP requests to an Apache Livy server (a REST API for
   Spark). No Spark binaries needed on the Airflow worker; Livy handles submission
   to the actual cluster.

3. **EmrAddStepsOperator / DatabricksRunNowOperator**: cloud-provider-specific
   operators that call AWS EMR or Databricks REST APIs.

The Airflow task's lifecycle mirrors the Spark job: the operator polls the job
status periodically and marks the task as success or failure based on the Spark
exit code.

---

## Q2. When would you use SparkSubmitOperator vs LivyOperator?

**Answer:**

| Scenario | Recommended Operator |
|---|---|
| Airflow workers can reach Spark master directly | `SparkSubmitOperator` |
| Spark runs on a remote cluster (no direct port access) | `LivyOperator` |
| Airflow runs in a container with no Spark client | `LivyOperator` |
| Spark on EMR with Livy installed | `LivyOperator` |
| Spark on Databricks | `DatabricksRunNowOperator` |
| Spark on GKE via Livy | `LivyOperator` |

**SparkSubmitOperator** is simpler — just a `spark-submit` wrapper — but requires
Spark client binaries, JAVA_HOME, and network access to the Spark master on the
Airflow worker.

**LivyOperator** is more flexible for containerised or cloud environments because
it only needs HTTP access to the Livy server port (typically 8998). The Spark
cluster itself can be completely private.

---

## Q3. How do you handle large output from a Spark job in Airflow?

**Answer:**
Never return large DataFrames or result sets via XCom. Spark jobs should:

1. **Write output to storage** (S3, GCS, HDFS, Delta Lake) inside the Spark job.
2. **Return only metadata** via XCom: the output path, row count, or job ID.

```python
# BAD: trying to return a DataFrame or large list via XCom
# XCom has a size limit (~48 KB by default, configurable with custom backends)

# GOOD: Spark job writes to S3, Airflow task receives the path
SparkSubmitOperator(
    task_id="transform",
    application="jobs/transform.py",
    application_args=["--output_path", "s3://bucket/output/{{ ds }}/"],
)

# A downstream task reads the output path from S3 directly
```

For large XCom, you can configure an S3/GCS XCom backend in Airflow, but it is
better practice to keep Spark output in storage and pass only references.

---

## Q4. What is the difference between the Airflow worker and the Spark driver?

**Answer:**

| Role | Airflow Worker | Spark Driver |
|---|---|---|
| Runs | The Airflow operator code | Spark application main program |
| Purpose | Submits job, polls status, handles retries | Coordinates Spark executors |
| Resource usage | Minimal (Python process) | Significant (SparkContext, DAG planning) |
| Location | Airflow cluster | Spark master (client mode) or executor node (cluster mode) |

With `SparkSubmitOperator` in **client mode**: the Airflow worker process IS the
Spark driver. This means the Airflow worker needs substantial memory and stays
active for the full duration of the job.

In **cluster mode**: the driver runs on the Spark cluster; the Airflow worker only
monitors the job status. Cluster mode is preferred in production to avoid
overloading Airflow workers.

---

## Q5. How do you manage resource allocation for Spark jobs in Airflow?

**Answer:**

1. **Per-operator settings**: set `executor_cores`, `executor_memory`,
   `num_executors`, `driver_memory` directly on `SparkSubmitOperator`.

2. **YARN queues**: use the `queue` field in the Spark connection config to route
   jobs to different YARN queues with capacity guarantees.

3. **Airflow pool**: create an Airflow Pool named `spark_heavy` with a small slot
   count (e.g., 3) and assign resource-intensive Spark tasks to it. This limits
   concurrent heavy Spark jobs regardless of the YARN queue.

4. **KubernetesExecutor resource requests**: if Airflow runs on Kubernetes, set
   `resources` on the task's pod template to ensure the Airflow worker pod has
   enough memory for client-mode driver.

---

## Q6. How would you submit a Spark job to AWS EMR from Airflow?

**Answer:**
Use the EMR operators from `apache-airflow-providers-amazon`:

```python
from airflow.providers.amazon.aws.operators.emr import (
    EmrCreateJobFlowOperator,
    EmrAddStepsOperator,
    EmrStepSensor,
    EmrTerminateJobFlowOperator,
)

# Step 1: Create EMR cluster (or use existing)
# Step 2: Add a Spark step (the actual job)
# Step 3: Wait for step completion with EmrStepSensor
# Step 4: Terminate cluster (if ephemeral)
```

Alternatively, use **LivyOperator** if Livy is installed on the EMR cluster,
which provides a cleaner REST-based interface and avoids the multi-operator
overhead.

---

## Q7. How do you pass Airflow run-time context (e.g., logical date) to a Spark job?

**Answer:**
Two mechanisms:

1. **`application_args`** — appended to `spark-submit` as command-line arguments,
   accessible in PySpark via `sys.argv`.

2. **`env_vars`** — injected as process environment variables, accessible in
   PySpark via `os.environ`.

Both support Jinja templating:
```python
SparkSubmitOperator(
    task_id="daily_etl",
    application="jobs/etl.py",
    application_args=["--date", "{{ ds }}", "--run_id", "{{ run_id }}"],
    env_vars={"AIRFLOW_ENV": "{{ var.value.environment }}"},
)
```

Never pass secrets directly as args (they appear in logs). Use Secrets Manager
or Vault instead, and have the Spark job fetch them at runtime.

---

## Q8. How do you monitor Spark jobs submitted from Airflow?

**Answer:**

- **Airflow task logs**: `SparkSubmitOperator` streams the `spark-submit` output
  (driver logs) directly to the Airflow task log. Set `verbose=True` for full logs.

- **Spark History Server**: completed Spark jobs are viewable in the Spark History
  Server UI. The Application ID is logged by the operator.

- **LivyOperator**: the operator logs the batch ID; you can view logs via the Livy
  REST API: `GET /batches/{id}/log`.

- **CloudWatch / Datadog**: emit Spark metrics via `spark.metrics.conf` to a
  StatsD or Prometheus endpoint.

- **Airflow callbacks**: attach `on_failure_callback` to send a Slack/PagerDuty
  alert when a Spark task fails.

---

## Q9. What happens when a Spark job fails? How does Airflow handle it?

**Answer:**
`SparkSubmitOperator` checks the `spark-submit` exit code:
- Exit code 0 → task succeeds.
- Non-zero exit code → Airflow marks task as `failed`.

`LivyOperator` polls the batch state:
- `"success"` → task succeeds.
- `"dead"` or `"error"` → `AirflowException` is raised → task fails.

Airflow then applies the standard retry logic:
- Retries the task up to `retries` times with `retry_delay` between attempts.
- On final failure, runs `on_failure_callback` if configured.
- Downstream tasks dependent on the failed task are skipped (unless `trigger_rule`
  is set to `TriggerRule.ALL_DONE` or similar).

---

## Q10. What are the trade-offs of on-premises Spark vs EMR for Airflow integration?

**Answer:**

| Aspect | On-Premises Spark | AWS EMR |
|---|---|---|
| Cluster availability | Always up (fixed cost) | Ephemeral (pay per run) |
| Setup | Complex (YARN/Hadoop) | Managed by AWS |
| Network access | Direct from Airflow worker | Via EMR master SG rules or Livy |
| Cold start | None | 3–8 min for cluster boot |
| Cost model | CapEx (servers) | OpEx (per-hour EC2) |
| Latest Spark version | Managed by your team | AWS releases quickly |
| Scaling | Manual or YARN dynamic alloc | EMR Managed Scaling |

Use **EMR** for bursty batch workloads where you want to pay only when jobs run.
Use **on-premises** when you have constant workloads and data gravity (data is
already in your datacenter).

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Next: Great Expectations** | [43_Great_Expectations](../43_Great_Expectations/Theory.md) |
