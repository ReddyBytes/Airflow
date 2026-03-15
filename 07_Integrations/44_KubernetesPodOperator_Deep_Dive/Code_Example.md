# KubernetesPodOperator Deep Dive — Code Examples

Production-ready patterns for every common KPO scenario.

---

## 1. Full KPO with All Common Parameters

```python
from datetime import datetime, timedelta
from airflow.sdk import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

with DAG(
    dag_id="kpo_full_example",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["kubernetes", "kpo"],
) as dag:

    full_kpo = KubernetesPodOperator(
        task_id="full_kpo_task",
        name="full-kpo-pod",
        namespace="data-pipelines",
        image="my-registry/etl-worker:2.1.0",
        image_pull_policy="Always",
        image_pull_secrets=[
            k8s.V1LocalObjectReference(name="registry-credentials")
        ],

        # Command
        cmds=["python", "-m", "etl.main"],
        arguments=["--date", "{{ ds }}", "--mode", "incremental"],

        # Environment
        env_vars={
            "ENVIRONMENT": "production",
            "LOG_LEVEL": "INFO",
            "RUN_ID": "{{ run_id }}",
        },

        # Secrets (inject all keys from K8s secret as env vars)
        env_from=[
            k8s.V1EnvFromSource(
                secret_ref=k8s.V1SecretEnvSource(name="etl-db-credentials")
            )
        ],

        # Resources
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "500m", "memory": "2Gi"},
            limits={"cpu": "2",    "memory": "8Gi"},
        ),

        # Volume for shared scratch space
        volumes=[
            k8s.V1Volume(
                name="scratch",
                empty_dir=k8s.V1EmptyDirVolumeSource(size_limit="5Gi"),
            )
        ],
        volume_mounts=[
            k8s.V1VolumeMount(name="scratch", mount_path="/tmp/scratch"),
        ],

        # Node placement
        node_selector={"workload-type": "batch"},
        tolerations=[
            k8s.V1Toleration(key="dedicated", operator="Equal",
                             value="batch", effect="NoSchedule")
        ],

        # Init container: wait for dependencies
        init_containers=[
            k8s.V1Container(
                name="wait-for-upstream",
                image="busybox:1.36",
                command=["sh", "-c",
                         "until wget -q -O- http://upstream-service/health; do sleep 5; done"],
            )
        ],

        # Behaviour
        is_delete_operator_pod=True,
        get_logs=True,
        log_events_on_failure=True,
        do_xcom_push=False,
        reattach_on_restart=True,
        deferrable=True,                    # release worker slot while pod runs

        # Retry
        retries=2,
        retry_delay=timedelta(minutes=5),
        execution_timeout=timedelta(hours=3),

        kubernetes_conn_id="kubernetes_default",
    )
```

---

## 2. GPU Training Task

```python
from datetime import datetime
from airflow.sdk import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

with DAG(
    dag_id="gpu_training",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["ml", "gpu"],
) as dag:

    train_model = KubernetesPodOperator(
        task_id="train_neural_net",
        name="gpu-training-pod",
        namespace="ml-workloads",
        image="my-registry/pytorch-trainer:cuda12.1",
        image_pull_policy="Always",

        cmds=["python", "train.py"],
        arguments=[
            "--model", "resnet50",
            "--epochs", "100",
            "--data-path", "s3://ml-bucket/training-data/{{ ds }}/",
            "--output-path", "s3://ml-bucket/models/resnet50/{{ ds }}/",
        ],

        # GPU resource request — node must have NVIDIA device plugin
        container_resources=k8s.V1ResourceRequirements(
            limits={
                "nvidia.com/gpu": "1",
                "memory": "32Gi",
                "cpu": "8",
            },
            requests={
                "nvidia.com/gpu": "1",
                "memory": "16Gi",
                "cpu": "4",
            },
        ),

        # Target GPU node pool
        node_selector={"accelerator": "nvidia-tesla-t4"},
        tolerations=[
            k8s.V1Toleration(
                key="nvidia.com/gpu",
                operator="Exists",
                effect="NoSchedule",
            )
        ],

        env_vars={
            "CUDA_VISIBLE_DEVICES": "0",
            "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:512",
        },
        env_from=[
            k8s.V1EnvFromSource(
                secret_ref=k8s.V1SecretEnvSource(name="aws-credentials-secret")
            )
        ],

        do_xcom_push=True,                  # capture model metrics
        is_delete_operator_pod=True,
        get_logs=True,
        deferrable=True,
        execution_timeout=None,             # no timeout for long GPU jobs
        kubernetes_conn_id="kubernetes_default",
    )
```

Inside `train.py` (container code):
```python
import json, os

# ... training logic ...

metrics = {"accuracy": 0.943, "loss": 0.214, "model_path": output_path}
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump(metrics, f)
```

---

## 3. Secret Injection — K8s Secret + Airflow Connection

```python
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

# --- Approach A: K8s Secret as environment variables ---
kpo_env_secret = KubernetesPodOperator(
    task_id="with_env_secret",
    name="env-secret-pod",
    namespace="data-pipelines",
    image="my-image:latest",
    env_from=[
        k8s.V1EnvFromSource(
            secret_ref=k8s.V1SecretEnvSource(name="snowflake-creds")
        )
    ],
    # Container sees: SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, SNOWFLAKE_ACCOUNT
    cmds=["python", "load.py"],
)

# --- Approach B: K8s Secret mounted as files ---
kpo_file_secret = KubernetesPodOperator(
    task_id="with_file_secret",
    name="file-secret-pod",
    namespace="data-pipelines",
    image="my-image:latest",
    volumes=[
        k8s.V1Volume(
            name="gcp-key",
            secret=k8s.V1SecretVolumeSource(secret_name="gcp-service-account"),
        )
    ],
    volume_mounts=[
        k8s.V1VolumeMount(name="gcp-key", mount_path="/secrets/gcp", read_only=True)
    ],
    env_vars={"GOOGLE_APPLICATION_CREDENTIALS": "/secrets/gcp/key.json"},
    cmds=["python", "bq_load.py"],
)
```

---

## 4. XCom Push from Pod + Dynamic Pod Names

```python
from datetime import datetime
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

def process_result(**context):
    result = context["ti"].xcom_pull(task_ids="data_processing_pod")
    rows = result.get("output_rows", 0)
    path = result.get("output_path", "")
    print(f"Pod processed {rows} rows, wrote to {path}")
    if rows == 0:
        raise ValueError("Pod produced zero output rows!")

with DAG(
    dag_id="kpo_xcom_demo",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:

    processing_pod = KubernetesPodOperator(
        task_id="data_processing_pod",
        # Dynamic name: includes logical date and try number to aid log correlation
        name="data-proc-{{ ds_nodash }}-{{ task_instance.try_number }}",
        namespace="data-pipelines",
        image="my-registry/data-processor:latest",
        cmds=["python", "process.py"],
        arguments=["--date", "{{ ds }}"],
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "1", "memory": "4Gi"},
            limits={"cpu": "4",  "memory": "16Gi"},
        ),
        do_xcom_push=True,              # read /airflow/xcom/return.json
        is_delete_operator_pod=True,
        get_logs=True,
        deferrable=True,
    )

    check_result = PythonOperator(
        task_id="check_result",
        python_callable=process_result,
    )

    processing_pod >> check_result
```

Container writes XCom before exit:
```python
# process.py (inside the container)
import json, os, sys

date = sys.argv[sys.argv.index("--date") + 1]
# ... process data ...
output_path = f"s3://bucket/output/{date}/"
rows_written = 42000

os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({"output_rows": rows_written, "output_path": output_path}, f)
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Previous: Great Expectations** | [43_Great_Expectations](../43_Great_Expectations/Theory.md) |
