# Airflow + Apache Spark — Code Examples

Working code patterns for every common Spark integration scenario.

---

## 1. SparkSubmitOperator — Basic DAG

```python
from datetime import datetime
from airflow.sdk import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

with DAG(
    dag_id="spark_basic_etl",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["spark", "etl"],
) as dag:

    run_etl = SparkSubmitOperator(
        task_id="run_daily_etl",
        application="/opt/airflow/jobs/daily_etl.py",
        conn_id="spark_default",
        conf={
            "spark.executor.memoryOverhead": "512m",
            "spark.sql.shuffle.partitions": "200",
            "spark.dynamicAllocation.enabled": "true",
        },
        application_args=["--date", "{{ ds }}"],
        executor_cores=2,
        executor_memory="4g",
        num_executors=5,
        driver_memory="2g",
        name="daily_etl_{{ ds }}",
        verbose=False,
        retries=2,
        retry_delay=60,
    )
```

The Spark job file (`daily_etl.py`) receives `--date` as `sys.argv`:

```python
# /opt/airflow/jobs/daily_etl.py
import sys
from pyspark.sql import SparkSession

def parse_args():
    args = {}
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith("--"):
            args[arg[2:]] = sys.argv[i + 1]
    return args

def main():
    params = parse_args()
    date = params["date"]

    spark = SparkSession.builder.appName(f"daily_etl_{date}").getOrCreate()

    df = spark.read.parquet(f"s3://raw-bucket/events/dt={date}/")
    result = df.filter(df.event_type == "purchase").groupBy("user_id").count()
    result.write.mode("overwrite").parquet(f"s3://processed-bucket/purchases/dt={date}/")

    spark.stop()

if __name__ == "__main__":
    main()
```

---

## 2. LivyOperator — Remote Spark Cluster

```python
from datetime import datetime
from airflow.sdk import DAG
from airflow.providers.apache.livy.operators.livy import LivyOperator

with DAG(
    dag_id="spark_via_livy",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["spark", "livy"],
) as dag:

    submit_job = LivyOperator(
        task_id="submit_spark_job",
        file="s3://my-bucket/jobs/transform.py",
        class_name=None,                        # PySpark (no class needed)
        args=["--date", "{{ ds }}", "--env", "{{ var.value.environment }}"],
        conf={
            "spark.executor.memory": "8g",
            "spark.executor.cores": "4",
            "spark.sql.shuffle.partitions": "400",
        },
        jars=["s3://my-bucket/jars/custom-udf.jar"],
        py_files=["s3://my-bucket/utils/helpers.zip"],
        num_executors=8,
        executor_cores=4,
        executor_memory="8g",
        driver_memory="4g",
        livy_conn_id="livy_default",
        polling_interval=20,                    # check status every 20s
    )
```

---

## 3. AWS EMR Full Pipeline

```python
from datetime import datetime
from airflow.sdk import DAG
from airflow.providers.amazon.aws.operators.emr import (
    EmrCreateJobFlowOperator,
    EmrAddStepsOperator,
    EmrTerminateJobFlowOperator,
)
from airflow.providers.amazon.aws.sensors.emr import EmrStepSensor

JOB_FLOW_OVERRIDES = {
    "Name": "airflow-etl-{{ ds }}",
    "ReleaseLabel": "emr-7.1.0",
    "Applications": [{"Name": "Spark"}],
    "Configurations": [
        {
            "Classification": "spark-defaults",
            "Properties": {
                "spark.executor.memory": "8g",
                "spark.sql.shuffle.partitions": "400",
            },
        }
    ],
    "Instances": {
        "InstanceGroups": [
            {
                "Name": "Master",
                "Market": "ON_DEMAND",
                "InstanceRole": "MASTER",
                "InstanceType": "m5.xlarge",
                "InstanceCount": 1,
            },
            {
                "Name": "Workers",
                "Market": "SPOT",
                "InstanceRole": "CORE",
                "InstanceType": "m5.2xlarge",
                "InstanceCount": 5,
            },
        ],
        "KeepJobFlowAliveWhenNoSteps": True,
        "TerminationProtected": False,
    },
    "JobFlowRole": "EMR_EC2_DefaultRole",
    "ServiceRole": "EMR_DefaultRole",
    "LogUri": "s3://my-emr-logs/",
}

SPARK_STEPS = [
    {
        "Name": "Daily ETL {{ ds }}",
        "ActionOnFailure": "CONTINUE",
        "HadoopJarStep": {
            "Jar": "command-runner.jar",
            "Args": [
                "spark-submit",
                "--deploy-mode", "cluster",
                "--master", "yarn",
                "--executor-memory", "8g",
                "--num-executors", "5",
                "s3://my-bucket/jobs/daily_etl.py",
                "--date", "{{ ds }}",
            ],
        },
    }
]

with DAG(
    dag_id="emr_spark_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["emr", "spark"],
) as dag:

    create_cluster = EmrCreateJobFlowOperator(
        task_id="create_emr_cluster",
        job_flow_overrides=JOB_FLOW_OVERRIDES,
        aws_conn_id="aws_default",
    )

    add_steps = EmrAddStepsOperator(
        task_id="add_spark_step",
        job_flow_id="{{ task_instance.xcom_pull('create_emr_cluster', key='return_value') }}",
        steps=SPARK_STEPS,
        aws_conn_id="aws_default",
    )

    watch_step = EmrStepSensor(
        task_id="watch_spark_step",
        job_flow_id="{{ task_instance.xcom_pull('create_emr_cluster', key='return_value') }}",
        step_id="{{ task_instance.xcom_pull('add_spark_step', key='return_value')[0] }}",
        aws_conn_id="aws_default",
        poke_interval=30,
    )

    terminate_cluster = EmrTerminateJobFlowOperator(
        task_id="terminate_emr_cluster",
        job_flow_id="{{ task_instance.xcom_pull('create_emr_cluster', key='return_value') }}",
        aws_conn_id="aws_default",
        trigger_rule="all_done",            # terminate even if step fails
    )

    create_cluster >> add_steps >> watch_step >> terminate_cluster
```

---

## 4. Passing Airflow Variables to Spark

```python
from datetime import datetime
from airflow.sdk import DAG
from airflow.models import Variable
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

with DAG(
    dag_id="spark_with_variables",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:

    # Variables can be templated directly in application_args
    run_job = SparkSubmitOperator(
        task_id="parameterised_spark",
        application="jobs/parameterised_etl.py",
        conn_id="spark_default",
        application_args=[
            "--date",        "{{ ds }}",
            "--run_id",      "{{ run_id }}",
            "--environment", "{{ var.value.environment }}",
            "--output",      "{{ var.value.output_bucket }}/{{ ds }}/",
        ],
        env_vars={
            # env_vars also support templating
            "AIRFLOW_DAG_RUN_ID": "{{ run_id }}",
            "PROCESSING_DATE":    "{{ ds }}",
        },
        conf={
            "spark.sql.shuffle.partitions": "{{ var.value.spark_shuffle_partitions | default('200') }}",
        },
    )
```

In the Spark job, consume both:

```python
# jobs/parameterised_etl.py
import sys
import os
from pyspark.sql import SparkSession

def get_arg(args_list, flag):
    idx = args_list.index(flag)
    return args_list[idx + 1]

args = sys.argv[1:]
date        = get_arg(args, "--date")
environment = get_arg(args, "--environment")
output_path = get_arg(args, "--output")

# Also available from env_vars
run_id = os.environ.get("AIRFLOW_DAG_RUN_ID", "unknown")

spark = SparkSession.builder \
    .appName(f"etl_{date}_{run_id}") \
    .getOrCreate()

df = spark.read.parquet(f"s3://raw/{date}/")
df.write.mode("overwrite").parquet(output_path)
spark.stop()
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Next: Great Expectations** | [43_Great_Expectations](../43_Great_Expectations/Theory.md) |
