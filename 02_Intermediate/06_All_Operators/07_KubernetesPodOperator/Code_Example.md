# KubernetesPodOperator — Code Examples

## 📂 Navigation
⬅️ **Prev: [Theory](./Theory.md)** | 🏠 **[Home](../../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: Simple Pod Task

This example runs a Python data processing script in a Kubernetes pod using a custom image. It demonstrates the minimal required configuration plus best practices for production use.

```python
# dags/k8s_example_01_simple_pod.py
from airflow.decorators import dag, task
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s
from datetime import datetime


@dag(
    dag_id="k8s_example_01_simple_pod",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["kubernetes", "example"],
)
def k8s_example_01_simple_pod():
    """
    Runs a simple Python script in a Kubernetes pod.

    Prerequisites:
    - Airflow running inside a Kubernetes cluster (in_cluster=True)
    - Airflow worker service account has permission to create/delete pods
      in the 'data-pipelines' namespace:
        kubectl create rolebinding airflow-pod-creator \
          --role=pod-creator \
          --serviceaccount=airflow:airflow-worker \
          --namespace=data-pipelines
    - Image 'data-team/etl-runner:1.2.0' available in the cluster's registry
    """

    @task
    def prepare(**context):
        """Prepare a run ID to pass to the pod."""
        run_id = context["dag_run"].run_id
        print(f"Starting K8s pipeline for run: {run_id}")
        return {"date": context["ds"], "run_id": run_id}

    # Run the ETL script in a pod
    run_etl = KubernetesPodOperator(
        task_id="run_etl_pod",
        # Pod name prefix — Kubernetes will append a unique suffix
        name="etl-runner",
        # Target namespace in the cluster
        namespace="data-pipelines",
        # Docker image to use (must be accessible from cluster nodes)
        image="data-team/etl-runner:1.2.0",
        # Image pull policy: IfNotPresent avoids pulling on every run
        # Use "Always" in development or when using mutable tags like 'latest'
        image_pull_policy="IfNotPresent",
        # cmds overrides the image ENTRYPOINT
        # arguments overrides the image CMD
        cmds=["python"],
        arguments=[
            "/app/etl.py",
            "--date", "{{ ds }}",
            "--run-id", "{{ dag_run.run_id }}",
            "--env", "production",
        ],
        # Environment variables as a list of V1EnvVar objects
        env_vars=[
            k8s.V1EnvVar(name="PROCESSING_DATE", value="{{ ds }}"),
            k8s.V1EnvVar(name="LOG_LEVEL", value="INFO"),
            # Literal value (not a secret — fine for non-sensitive config)
            k8s.V1EnvVar(name="OUTPUT_BUCKET", value="s3://my-company-data"),
        ],
        # Stream pod logs to the Airflow task log
        get_logs=True,
        # Delete pod after it finishes (keep=False is the production default)
        is_delete_operator_pod=True,
        # Auth: use in-cluster service account (Airflow runs in the cluster)
        in_cluster=True,
        # Labels for grouping/querying pods in kubectl
        labels={
            "app": "airflow-task",
            "dag-id": "k8s_example_01_simple_pod",
            "managed-by": "airflow",
        },
        # Annotations for tooling (e.g. Datadog, Prometheus scraping)
        annotations={
            "prometheus.io/scrape": "false",
        },
        # Seconds to wait for pod to reach Running state before failing
        startup_timeout_seconds=120,
    )

    @task
    def check_result(**context):
        """Verify the pod completed and log the outcome."""
        print(f"ETL pod completed for {context['ds']}")
        print(f"Run ID: {context['dag_run'].run_id}")

    info = prepare()
    info >> run_etl >> check_result()


k8s_example_01_simple_pod()
```

---

## Example 2: Pod with Resource Limits and Environment Variables from Secrets

This example demonstrates a production-grade pod task with:
- CPU and memory requests/limits
- Secrets mounted as environment variables
- ConfigMap-based configuration
- XCom push from the pod
- Node selector to target specific node pools (e.g. high-memory nodes)

```python
# dags/k8s_example_02_resource_limits_and_env.py
import json
from airflow.decorators import dag, task
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s
from datetime import datetime


@dag(
    dag_id="k8s_example_02_resource_limits",
    schedule="@weekly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["kubernetes", "example"],
)
def k8s_example_02_resource_limits():
    """
    Production-grade KubernetesPodOperator with resource limits, secrets,
    node affinity, and XCom output.

    Kubernetes prerequisites:
    1. Secret for database credentials:
       kubectl create secret generic db-credentials \
         --from-literal=host=postgres.internal \
         --from-literal=password=supersecret \
         --namespace data-pipelines

    2. Secret for cloud credentials:
       kubectl create secret generic aws-credentials \
         --from-literal=access_key_id=AKIAxxx \
         --from-literal=secret_access_key=yyy \
         --namespace data-pipelines

    3. ConfigMap for application config:
       kubectl create configmap etl-config \
         --from-literal=output_bucket=s3://company-data/processed \
         --from-literal=batch_size=5000 \
         --namespace data-pipelines
    """

    # Resource requirements for the heavy ML workload
    # requests: what the pod is guaranteed
    # limits: the maximum it can use
    resource_requirements = k8s.V1ResourceRequirements(
        requests={
            "cpu": "1000m",      # 1 CPU core guaranteed
            "memory": "2Gi",     # 2 GB RAM guaranteed
        },
        limits={
            "cpu": "4000m",      # Max 4 CPU cores
            "memory": "8Gi",     # Max 8 GB RAM — pod is killed if it exceeds this
        },
    )

    # Environment variables — mix of literals, secrets, and ConfigMap values
    env_vars = [
        # Literal values (non-sensitive config)
        k8s.V1EnvVar(name="PROCESSING_DATE", value="{{ ds }}"),
        k8s.V1EnvVar(name="RUN_ID", value="{{ dag_run.run_id }}"),
        k8s.V1EnvVar(name="ENVIRONMENT", value="production"),

        # Database credentials from a Kubernetes Secret
        k8s.V1EnvVar(
            name="DB_HOST",
            value_from=k8s.V1EnvVarSource(
                secret_key_ref=k8s.V1SecretKeySelector(
                    name="db-credentials",     # Secret name in K8s
                    key="host",                # Key within the secret
                )
            ),
        ),
        k8s.V1EnvVar(
            name="DB_PASSWORD",
            value_from=k8s.V1EnvVarSource(
                secret_key_ref=k8s.V1SecretKeySelector(
                    name="db-credentials",
                    key="password",
                )
            ),
        ),

        # AWS credentials from a Kubernetes Secret
        k8s.V1EnvVar(
            name="AWS_ACCESS_KEY_ID",
            value_from=k8s.V1EnvVarSource(
                secret_key_ref=k8s.V1SecretKeySelector(
                    name="aws-credentials",
                    key="access_key_id",
                )
            ),
        ),
        k8s.V1EnvVar(
            name="AWS_SECRET_ACCESS_KEY",
            value_from=k8s.V1EnvVarSource(
                secret_key_ref=k8s.V1SecretKeySelector(
                    name="aws-credentials",
                    key="secret_access_key",
                )
            ),
        ),

        # Values from a ConfigMap
        k8s.V1EnvVar(
            name="OUTPUT_BUCKET",
            value_from=k8s.V1EnvVarSource(
                config_map_key_ref=k8s.V1ConfigMapKeySelector(
                    name="etl-config",
                    key="output_bucket",
                )
            ),
        ),
        k8s.V1EnvVar(
            name="BATCH_SIZE",
            value_from=k8s.V1EnvVarSource(
                config_map_key_ref=k8s.V1ConfigMapKeySelector(
                    name="etl-config",
                    key="batch_size",
                )
            ),
        ),
    ]

    # Volumes for shared storage and the XCom output directory
    volumes = [
        # emptyDir volume — ephemeral scratch space local to this pod
        k8s.V1Volume(
            name="scratch",
            empty_dir=k8s.V1EmptyDirVolumeSource(medium="", size_limit="5Gi"),
        ),
        # XCom volume — required when do_xcom_push=True
        k8s.V1Volume(
            name="xcom",
            empty_dir=k8s.V1EmptyDirVolumeSource(),
        ),
    ]

    volume_mounts = [
        k8s.V1VolumeMount(
            name="scratch",
            mount_path="/scratch",
        ),
        # Mount the xcom volume at /airflow/xcom so the container can write return.json
        k8s.V1VolumeMount(
            name="xcom",
            mount_path="/airflow/xcom",
        ),
    ]

    # Run on nodes labeled with 'workload-type: compute-intensive'
    # This routes the pod to a dedicated high-CPU node pool
    node_selector = {
        "workload-type": "compute-intensive",
    }

    # Allow scheduling on nodes with the 'dedicated=batch:NoSchedule' taint
    tolerations = [
        k8s.V1Toleration(
            key="dedicated",
            operator="Equal",
            value="batch",
            effect="NoSchedule",
        ),
    ]

    process_data = KubernetesPodOperator(
        task_id="process_weekly_data",
        name="weekly-processor",
        namespace="data-pipelines",
        image="data-team/weekly-processor:2.0.1",
        image_pull_policy="IfNotPresent",
        # Private registry credentials
        image_pull_secrets=[
            k8s.V1LocalObjectReference(name="registry-credentials")
        ],
        cmds=["python"],
        arguments=[
            "/app/process_weekly.py",
            "--week-start", "{{ data_interval_start.start_of('week').to_date_string() }}",
            "--week-end", "{{ data_interval_end.to_date_string() }}",
            "--output-xcom",  # Flag telling the script to write /airflow/xcom/return.json
        ],
        env_vars=env_vars,
        volumes=volumes,
        volume_mounts=volume_mounts,
        resources=resource_requirements,
        node_selector=node_selector,
        tolerations=tolerations,
        # Service account with permissions for this specific workload
        service_account_name="batch-processor",
        get_logs=True,
        is_delete_operator_pod=True,
        # Pod will write its result to /airflow/xcom/return.json
        # Airflow reads this file and pushes it as XCom
        do_xcom_push=True,
        in_cluster=True,
        startup_timeout_seconds=180,  # Give the pod 3 minutes to start
        labels={
            "app": "weekly-processor",
            "team": "data-engineering",
            "cost-center": "data-platform",
        },
        # Retry once on failure (pod will be recreated from scratch)
        retries=1,
    )

    @task
    def handle_results(**context):
        """
        Process the XCom output written by the pod to /airflow/xcom/return.json.

        The container script wrote something like:
        {
            "records_processed": 125000,
            "partitions_written": 7,
            "output_path": "s3://company-data/processed/weekly/2025-W11/",
            "duration_seconds": 847
        }
        """
        result = context["ti"].xcom_pull(task_ids="process_weekly_data")

        if result is None:
            raise ValueError("Pod did not produce XCom output — check pod logs")

        # result may be a dict (if Airflow deserialized it) or a JSON string
        if isinstance(result, str):
            result = json.loads(result)

        print(f"Weekly processing complete:")
        print(f"  Records:    {result.get('records_processed'):,}")
        print(f"  Partitions: {result.get('partitions_written')}")
        print(f"  Output:     {result.get('output_path')}")
        print(f"  Duration:   {result.get('duration_seconds')}s")

        if result.get("records_processed", 0) < 1000:
            import warnings
            warnings.warn(
                f"Unexpectedly low record count: {result.get('records_processed')}"
            )

        return result

    @task
    def notify_downstream(result: dict, **context):
        """Trigger downstream systems now that weekly data is available."""
        output_path = result.get("output_path")
        week = context["data_interval_start"].start_of("week").to_date_string()
        print(f"Notifying downstream: week {week} data available at {output_path}")

    result = handle_results()
    process_data >> result
    notify_downstream(result)


k8s_example_02_resource_limits()
```

**Container script pattern for XCom output (`/app/process_weekly.py`):**

```python
# What the container script needs to do to push XCom
import json
import os
import sys

def main():
    # ... do all the actual work ...
    records_processed = 125000
    output_path = "s3://company-data/processed/weekly/2025-W11/"

    # Write XCom output if flag is set
    if "--output-xcom" in sys.argv:
        os.makedirs("/airflow/xcom", exist_ok=True)
        with open("/airflow/xcom/return.json", "w") as f:
            json.dump({
                "records_processed": records_processed,
                "partitions_written": 7,
                "output_path": output_path,
                "duration_seconds": 847,
            }, f)

if __name__ == "__main__":
    main()
```
