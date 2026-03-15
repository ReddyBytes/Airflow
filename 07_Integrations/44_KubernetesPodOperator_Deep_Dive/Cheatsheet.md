# KubernetesPodOperator Deep Dive — Cheatsheet

The `KubernetesPodOperator` (KPO) launches a Kubernetes pod, runs a container,
waits for it to complete, and optionally captures logs and XCom output. It is the
most flexible Airflow operator: if you can containerise a workload, KPO can run it.

---

## Provider Package

```bash
pip install apache-airflow-providers-cncf-kubernetes
```

---

## Full Parameter Reference

```python
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

KubernetesPodOperator(
    # ── Identity ──────────────────────────────────────────────────────────────
    task_id="my_task",
    name="my-pod",                          # pod name prefix (unique per run via random suffix)
    namespace="data-pipelines",             # K8s namespace

    # ── Container image ───────────────────────────────────────────────────────
    image="my-registry/my-image:1.0.0",     # must be pullable from the K8s cluster
    image_pull_policy="Always",             # Always | IfNotPresent | Never
    image_pull_secrets=[
        k8s.V1LocalObjectReference(name="registry-secret")
    ],

    # ── Command ───────────────────────────────────────────────────────────────
    cmds=["python"],                        # entrypoint override
    arguments=["run.py", "--date", "{{ ds }}"],

    # ── Environment variables ─────────────────────────────────────────────────
    env_vars={
        "ENVIRONMENT": "production",
        "PROCESSING_DATE": "{{ ds }}",
    },

    # ── Secrets ───────────────────────────────────────────────────────────────
    secrets=[
        k8s.V1EnvFromSource(
            secret_ref=k8s.V1SecretEnvSource(name="db-credentials")
        ),
    ],

    # ── Resource requests & limits ────────────────────────────────────────────
    container_resources=k8s.V1ResourceRequirements(
        requests={"cpu": "500m", "memory": "1Gi"},
        limits={"cpu": "2",    "memory": "4Gi"},
    ),

    # ── Volumes ───────────────────────────────────────────────────────────────
    volumes=[
        k8s.V1Volume(
            name="shared-data",
            persistent_volume_claim=k8s.V1PersistentVolumeClaimVolumeSource(
                claim_name="airflow-pvc"
            ),
        ),
    ],
    volume_mounts=[
        k8s.V1VolumeMount(
            name="shared-data",
            mount_path="/data",
            read_only=False,
        ),
    ],

    # ── Scheduling ────────────────────────────────────────────────────────────
    node_selector={"node.kubernetes.io/instance-type": "m5.2xlarge"},
    affinity=k8s.V1Affinity(
        node_affinity=k8s.V1NodeAffinity(
            required_during_scheduling_ignored_during_execution=k8s.V1NodeSelector(
                node_selector_terms=[
                    k8s.V1NodeSelectorTerm(
                        match_expressions=[
                            k8s.V1NodeSelectorRequirement(
                                key="workload-type",
                                operator="In",
                                values=["batch"],
                            )
                        ]
                    )
                ]
            )
        )
    ),
    tolerations=[
        k8s.V1Toleration(key="dedicated", operator="Equal", value="batch", effect="NoSchedule")
    ],

    # ── Init containers ───────────────────────────────────────────────────────
    init_containers=[
        k8s.V1Container(
            name="wait-for-db",
            image="busybox",
            command=["sh", "-c", "until nc -z db-host 5432; do sleep 2; done"],
        )
    ],

    # ── Behaviour ─────────────────────────────────────────────────────────────
    is_delete_operator_pod=True,            # delete pod after completion
    get_logs=True,                          # stream pod logs to Airflow task log
    do_xcom_push=False,                     # set True to capture XCom from pod
    log_events_on_failure=True,             # log K8s events on pod failure
    reattach_on_restart=True,               # resume monitoring if scheduler restarts

    # ── Retry ─────────────────────────────────────────────────────────────────
    retries=2,
    retry_delay=30,
    execution_timeout=timedelta(hours=2),

    # ── Connection ────────────────────────────────────────────────────────────
    kubernetes_conn_id="kubernetes_default",
)
```

---

## XCom from a Pod

When `do_xcom_push=True`, the operator reads `/airflow/xcom/return.json` from
the container before it exits:

```python
# Dockerfile or entrypoint script
import json, os

result = {"processed_rows": 42000, "output_path": "s3://bucket/output/"}
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump(result, f)
```

Downstream tasks receive this dict via `xcom_pull`:
```python
value = ti.xcom_pull(task_ids="my_kpo_task")  # returns the dict
```

---

## Secrets Patterns

```python
# Pattern 1: Inject K8s Secret as environment variables
from kubernetes.client import models as k8s

env_from = [k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name="my-secret"))]

# Pattern 2: Mount K8s Secret as a file
secret_volume = k8s.V1Volume(
    name="secret-vol",
    secret=k8s.V1SecretVolumeSource(secret_name="my-secret"),
)
secret_mount = k8s.V1VolumeMount(name="secret-vol", mount_path="/secrets", read_only=True)
# Container reads: open("/secrets/my-key").read()

# Pattern 3: Airflow Connection via environment variable
# The Airflow scheduler injects AIRFLOW_CONN_<CONN_ID> into pods automatically
# when using KubernetesExecutor (not available with KPO explicitly)
```

---

## GPU Workloads

```python
KubernetesPodOperator(
    task_id="train_model",
    image="my-registry/pytorch-training:1.0",
    container_resources=k8s.V1ResourceRequirements(
        limits={"nvidia.com/gpu": "1"},         # request 1 GPU
        requests={"memory": "16Gi", "cpu": "4"},
    ),
    node_selector={"accelerator": "nvidia-tesla-t4"},
    tolerations=[
        k8s.V1Toleration(key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")
    ],
    env_vars={"CUDA_VISIBLE_DEVICES": "0"},
)
```

The node must have the NVIDIA device plugin installed and GPU nodes tainted
appropriately.

---

## Dynamic Pod Names

```python
import uuid
KubernetesPodOperator(
    task_id="dynamic_name",
    name=f"etl-pod-{uuid.uuid4().hex[:8]}",   # unique name per run
    # OR use Jinja:
    name="etl-{{ run_id | slugify }}-{{ task_instance.try_number }}",
)
```

KPO appends a random suffix automatically, so uniqueness is already guaranteed.
Custom names are useful for log correlation.

---

## Debugging Failed Pods

```bash
# Get logs after pod fails (before is_delete_operator_pod deletes it)
kubectl logs <pod-name> -n data-pipelines

# Describe pod for events (image pull errors, OOM, etc.)
kubectl describe pod <pod-name> -n data-pipelines

# Set is_delete_operator_pod=False temporarily for debugging
# Then manually delete: kubectl delete pod <pod-name> -n data-pipelines
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Previous: Great Expectations** | [43_Great_Expectations](../43_Great_Expectations/Theory.md) |
