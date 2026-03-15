# Airflow + Apache Spark — Cheatsheet

Airflow does not run Spark jobs itself — it **orchestrates** them. Airflow decides
when to start a job, passes parameters, waits for completion, and handles retries
and failure alerting. Spark does the heavy distributed computation.

---

## Provider Package

```bash
pip install apache-airflow-providers-apache-spark
# For Livy (remote Spark via REST)
pip install apache-airflow-providers-apache-livy
# For EMR
pip install apache-airflow-providers-amazon
```

---

## Spark Operators at a Glance

| Operator | Provider | How it submits | Best for |
|---|---|---|---|
| `SparkSubmitOperator` | apache-spark | `spark-submit` CLI on the Airflow worker | Local / YARN / Standalone clusters |
| `SparkJDBCOperator` | apache-spark | JDBC query via Spark | SQL-on-Spark |
| `LivyOperator` | apache-livy | HTTP REST to Apache Livy server | Remote Spark (Databricks, EMR, etc.) |
| `EmrAddStepsOperator` | amazon | AWS EMR Step API | EMR clusters |
| `DatabricksRunNowOperator` | databricks | Databricks REST API | Databricks jobs |

---

## SparkSubmitOperator — Key Parameters

```python
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

SparkSubmitOperator(
    task_id="run_etl",
    application="/opt/spark/jobs/my_etl.py",    # path on Airflow worker or HDFS
    conn_id="spark_default",                     # Airflow connection to Spark master
    conf={                                        # spark.xxx overrides
        "spark.executor.memoryOverhead": "512m",
        "spark.sql.shuffle.partitions": "200",
    },
    application_args=["--date", "{{ ds }}"],     # passed as sys.argv
    executor_cores=2,
    executor_memory="4g",
    num_executors=5,
    driver_memory="2g",
    name="{{ task_instance.task_id }}_{{ ds }}",
    verbose=True,
    env_vars={"HADOOP_CONF_DIR": "/etc/hadoop/conf"},
    jars="/opt/jars/my-lib.jar",
    packages="org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0",
    py_files="/opt/spark/utils.zip",
)
```

---

## Connection Setup: `spark_default`

In the Airflow UI → **Admin → Connections**:

| Field | Value |
|---|---|
| Conn ID | `spark_default` |
| Conn Type | `Spark` |
| Host | `spark://spark-master` |
| Port | `7077` (standalone) or `yarn` |
| Extra | `{"queue": "default", "deploy-mode": "client"}` |

For YARN:
```
Host: yarn
Extra: {"queue": "data_team", "spark-home": "/opt/spark"}
```

---

## LivyOperator — Key Parameters

```python
from airflow.providers.apache.livy.operators.livy import LivyOperator

LivyOperator(
    task_id="livy_job",
    file="s3://my-bucket/jobs/etl.py",          # job file URI accessible by Livy
    class_name=None,                             # None for PySpark
    args=["--date", "{{ ds }}"],
    conf={"spark.executor.memory": "8g"},
    jars=["s3://my-bucket/jars/my-lib.jar"],
    py_files=["s3://my-bucket/utils.zip"],
    num_executors=4,
    executor_cores=2,
    executor_memory="8g",
    driver_memory="4g",
    livy_conn_id="livy_default",
    polling_interval=30,                         # seconds between status checks
)
```

---

## Connection Setup: `livy_default`

| Field | Value |
|---|---|
| Conn ID | `livy_default` |
| Conn Type | `HTTP` |
| Host | `http://livy-server` |
| Port | `8998` |
| Extra | `{"auth": "kerberos"}` (if secured) |

---

## Livy REST API (reference)

```bash
# Submit a batch job
curl -X POST http://livy-server:8998/batches \
  -H "Content-Type: application/json" \
  -d '{
    "file": "s3://bucket/job.py",
    "args": ["--date", "2024-01-01"],
    "numExecutors": 4,
    "executorMemory": "8g",
    "conf": {"spark.sql.shuffle.partitions": "400"}
  }'

# Check status
curl http://livy-server:8998/batches/{id}

# Get logs
curl http://livy-server:8998/batches/{id}/log
```

---

## Passing Airflow Variables to Spark Jobs

```python
# Method 1: application_args with Jinja
SparkSubmitOperator(
    task_id="etl",
    application="jobs/etl.py",
    application_args=[
        "--date", "{{ ds }}",
        "--env",  "{{ var.value.environment }}",
        "--run_id", "{{ run_id }}",
    ],
)

# Method 2: env_vars
SparkSubmitOperator(
    task_id="etl",
    application="jobs/etl.py",
    env_vars={
        "PROCESSING_DATE": "{{ ds }}",
        "S3_BUCKET": "{{ var.value.s3_bucket }}",
    },
)
```

In the Spark job (PySpark):
```python
import sys
import os

date = sys.argv[sys.argv.index("--date") + 1]   # from application_args
bucket = os.environ["S3_BUCKET"]                # from env_vars
```

---

## EMR Integration (SparkSubmitOperator on EMR)

```python
from airflow.providers.amazon.aws.operators.emr import (
    EmrCreateJobFlowOperator,
    EmrAddStepsOperator,
    EmrStepSensor,
    EmrTerminateJobFlowOperator,
)
```

See [Code_Example.md](./Code_Example.md) for a full EMR pipeline.

---

## Common Pitfalls

| Pitfall | Fix |
|---|---|
| Airflow worker needs `spark-submit` binary | Install Spark client on worker, or use LivyOperator |
| Large XCom from Spark output | Never return large DataFrames; write to S3/GCS instead |
| Spark job timeout | Set `execution_timeout` on the operator AND `spark.network.timeout` |
| Log verbosity | Set `verbose=False` in SparkSubmitOperator to reduce log noise |
| YARN queue starvation | Set `queue` in Extra connection config |

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Next: Great Expectations** | [43_Great_Expectations](../43_Great_Expectations/Theory.md) |
