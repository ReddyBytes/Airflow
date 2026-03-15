# KubernetesPodOperator — Cheatsheet

> Quick reference for Apache Airflow 3. Provider: `apache-airflow-providers-cncf-kubernetes`

---

## Install

```bash
pip install apache-airflow-providers-cncf-kubernetes
```

---

## Import

```python
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret
from kubernetes.client import (
    V1ResourceRequirements,
    V1EnvVar, V1EnvVarSource, V1SecretKeySelector,
    V1Volume, V1VolumeMount, V1ConfigMapVolumeSource, V1PersistentVolumeClaimVolumeSource,
    V1Affinity, V1NodeAffinity, V1NodeSelector, V1NodeSelectorTerm, V1NodeSelectorRequirement,
    V1InitContainer,
)
```

---

## Key Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Pod name prefix in Kubernetes |
| `image` | `str` | required | Container image, e.g. `"myrepo/job:v1.2.3"` |
| `namespace` | `str` | `"default"` | Kubernetes namespace for the Pod |
| `cmds` | `list[str]` | `None` | Entrypoint command (overrides image ENTRYPOINT) |
| `arguments` | `list[str]` | `None` | Arguments passed to `cmds` (overrides image CMD) |
| `env_vars` | `dict \| list` | `None` | Environment variables: dict for simple, list of `V1EnvVar` for secrets |
| `secrets` | `list[Secret]` | `None` | Airflow `Secret` objects mapped to env vars or volume files |
| `container_resources` | `V1ResourceRequirements` | `None` | CPU/memory requests and limits |
| `is_delete_operator_pod` | `bool` | `True` | Delete Pod after completion |
| `get_logs` | `bool` | `True` | Stream Pod stdout/stderr to Airflow task logs |
| `do_xcom_push` | `bool` | `False` | Enable XCom via sidecar reading `/airflow/xcom/return.json` |
| `kubernetes_conn_id` | `str` | `"kubernetes_default"` | Airflow Connection for kubeconfig |
| `affinity` | `V1Affinity` | `None` | Pod scheduling affinity/anti-affinity rules |
| `tolerations` | `list` | `None` | K8s node taints the Pod tolerates |
| `node_selector` | `dict` | `None` | Schedule on nodes with these labels |
| `volumes` | `list[V1Volume]` | `None` | Kubernetes volumes to attach |
| `volume_mounts` | `list[V1VolumeMount]` | `None` | Volume mount paths in the container |
| `init_containers` | `list[V1InitContainer]` | `None` | Containers that run before the main container |
| `service_account_name` | `str` | `None` | Kubernetes ServiceAccount for the Pod |
| `image_pull_secrets` | `list` | `None` | Secrets for pulling from private registries |
| `labels` | `dict` | `None` | Kubernetes labels added to the Pod |
| `full_pod_spec` | `V1Pod` | `None` | Override the entire Pod spec (advanced) |

---

## Code Patterns

### Basic Pod

```python
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

basic_pod = KubernetesPodOperator(
    task_id="basic_job",
    name="basic-job",
    image="python:3.11-slim",
    namespace="airflow",
    cmds=["python", "-c"],
    arguments=["print('Hello from Kubernetes!')"],
    is_delete_operator_pod=True,
    get_logs=True,
)
```

### With Resource Limits

```python
from kubernetes.client import V1ResourceRequirements

ml_training = KubernetesPodOperator(
    task_id="train_model",
    name="trainer",
    image="myrepo/trainer:v2.1.0",
    namespace="ml",
    arguments=["--epochs", "100", "--date", "{{ ds }}"],
    container_resources=V1ResourceRequirements(
        requests={"cpu": "4", "memory": "16Gi"},
        limits={"cpu": "8", "memory": "32Gi", "nvidia.com/gpu": "1"},
    ),
    is_delete_operator_pod=True,
    get_logs=True,
)
```

### With Kubernetes Secrets

```python
from airflow.providers.cncf.kubernetes.secret import Secret

# Map K8s Secret key → environment variable
db_password = Secret(
    deploy_type="env",        # inject as env var
    deploy_target="DB_PASSWORD",
    secret="db-credentials",  # K8s Secret object name
    key="password",           # key within the Secret
)

api_key = Secret(
    deploy_type="env",
    deploy_target="API_KEY",
    secret="api-credentials",
    key="key",
)

secure_pod = KubernetesPodOperator(
    task_id="secure_job",
    name="secure-job",
    image="myrepo/job:latest",
    namespace="airflow",
    secrets=[db_password, api_key],
    is_delete_operator_pod=True,
)
```

### With XCom Push

```python
# Your container must write to /airflow/xcom/return.json:
# import json, pathlib
# pathlib.Path("/airflow/xcom/return.json").write_text(json.dumps({"rows": 1234}))

xcom_pod = KubernetesPodOperator(
    task_id="compute_result",
    name="compute-result",
    image="myrepo/compute:latest",
    namespace="airflow",
    do_xcom_push=True,
    is_delete_operator_pod=True,
)
# Downstream: ti.xcom_pull(task_ids="compute_result") → {"rows": 1234}
```

### With Volume Mount (PVC)

```python
from kubernetes.client import V1Volume, V1VolumeMount, V1PersistentVolumeClaimVolumeSource

KubernetesPodOperator(
    task_id="with_pvc",
    name="pvc-job",
    image="myrepo/job:latest",
    namespace="airflow",
    volumes=[
        V1Volume(
            name="data-volume",
            persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                claim_name="my-pvc"
            )
        )
    ],
    volume_mounts=[
        V1VolumeMount(
            name="data-volume",
            mount_path="/data",
            read_only=False,
        )
    ],
    is_delete_operator_pod=True,
)
```

### With Node Affinity (GPU Scheduling)

```python
from kubernetes.client import (
    V1Affinity, V1NodeAffinity, V1NodeSelector,
    V1NodeSelectorTerm, V1NodeSelectorRequirement
)

gpu_affinity = V1Affinity(
    node_affinity=V1NodeAffinity(
        required_during_scheduling_ignored_during_execution=V1NodeSelector(
            node_selector_terms=[
                V1NodeSelectorTerm(
                    match_expressions=[
                        V1NodeSelectorRequirement(
                            key="accelerator", operator="In", values=["nvidia-v100"]
                        )
                    ]
                )
            ]
        )
    )
)

KubernetesPodOperator(
    task_id="gpu_job",
    name="gpu-job",
    image="myrepo/trainer:cuda12",
    namespace="ml",
    affinity=gpu_affinity,
    container_resources=V1ResourceRequirements(
        limits={"nvidia.com/gpu": "1"}
    ),
    is_delete_operator_pod=True,
)
```

---

## KPO vs DockerOperator vs KubernetesExecutor

| Dimension | KubernetesPodOperator | DockerOperator | KubernetesExecutor |
|-----------|----------------------|----------------|--------------------|
| What it does | Runs a custom container as a task | Runs a container on a Docker host | Runs every Airflow task in a K8s Pod |
| Custom image per task | Yes | Yes | No (uses Airflow worker image) |
| Infrastructure needed | K8s cluster | Docker daemon | K8s cluster |
| Autoscaling | Yes (cluster autoscaler) | No (single host) | Yes |
| GPU / special hardware | Yes (node affinity) | Limited | No |
| K8s Secrets natively | Yes | No | Partial (via executor_config) |
| Local dev experience | Requires minikube/kind | Excellent | Requires minikube/kind |
| Recommended for production | Yes | Small/single-node only | Yes (combined with KPO) |

---

## When to Use KubernetesPodOperator

- ML model training requiring GPU or large RAM.
- Tasks needing isolated Python/R/Java/Go environments with specific dependency versions.
- Workloads requiring native Kubernetes secret and config management.
- Burst workloads that benefit from cluster autoscaling.
- Any task where DockerOperator's single-host limitation is a concern.

## When to Avoid KubernetesPodOperator

- Local development without a Kubernetes cluster (use DockerOperator instead).
- Simple Python tasks — unnecessary overhead; use PythonOperator or BashOperator.
- Very short-lived tasks (< 5 seconds) — Pod startup overhead is significant.
- When the data engineering team has no Kubernetes expertise.

---

## XCom via Sidecar — How It Works

```
Main Container          Sidecar (xcom)
──────────────          ──────────────
Writes output to  →     Shared volume   →  Airflow reads file
/airflow/xcom/          /airflow/xcom/     and pushes to XCom
return.json             return.json
```

The sidecar container is automatically injected by Airflow when `do_xcom_push=True`. Your job: write valid JSON to `/airflow/xcom/return.json` before the main container exits.

---

## Golden Rules

1. Always pin image tags — never use `latest` in production.
2. Set `container_resources` (requests + limits) for every Pod to enable proper scheduling.
3. Use Kubernetes Secrets (via `secrets` parameter) for all sensitive values.
4. Set `is_delete_operator_pod=True` in production; use `False` only for debugging.
5. Use `get_logs=True` — you will thank yourself when debugging failures.
6. For XCom: keep `/airflow/xcom/return.json` small — write large outputs to object storage and push the path.
7. Use namespaces and RBAC to limit what Airflow's ServiceAccount can create in the cluster.

---

## 📂 Navigation

| | |
|---|---|
| **Parent folder** | [06_All_Operators](../) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Prev operator** | [06_DockerOperator](../06_DockerOperator/) |
| **Next operator** | [08_TriggerDagRunOperator](../08_TriggerDagRunOperator/) |
| **Section root** | [02_Intermediate](../../) |
