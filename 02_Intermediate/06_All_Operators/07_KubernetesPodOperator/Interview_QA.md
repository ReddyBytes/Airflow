# KubernetesPodOperator — Interview Q&A

> Study guide for Apache Airflow 3. Story-first, beginner-friendly.

---

## Beginner

**Q1. What is KubernetesPodOperator?**

KubernetesPodOperator (KPO) lets Airflow launch a Kubernetes Pod for each task. Instead of running code inside an Airflow worker process, Airflow calls the Kubernetes API to create a Pod, waits for it to complete, streams its logs, and optionally retrieves its output. Once the Pod finishes (success or failure), Airflow marks the task accordingly.

Think of it as DockerOperator's cloud-native cousin: same idea (run a container), but powered by a full Kubernetes cluster instead of a single Docker daemon.

**Q2. How does KubernetesPodOperator differ from DockerOperator?**

The conceptual job is similar — run a container image as a task — but the execution environment is completely different:

- **DockerOperator** calls the Docker API on the machine where the Airflow worker runs. It is limited to one host's CPU and RAM.
- **KubernetesPodOperator** calls the Kubernetes API. The cluster scheduler can place the Pod on any available node, giving you access to the cluster's total resources, autoscaling, and native secret/config management.

KPO is the production-grade choice. DockerOperator is easier for local development.

**Q3. What is the `namespace` parameter?**

`namespace` is the Kubernetes namespace where the Pod will be created. Namespaces are Kubernetes's way of organising and isolating resources within a cluster (similar to folders on a filesystem). Common values: `"default"`, `"airflow"`, `"data-platform"`. Using a dedicated namespace for Airflow Pods makes access control and resource quotas easier to manage.

**Q4. What is the minimum configuration needed to run a KubernetesPodOperator?**

At minimum you need: a task `name`, an `image`, and a `namespace`:

```python
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

KubernetesPodOperator(
    task_id="minimal_pod",
    name="minimal-pod",          # Pod name prefix in Kubernetes
    image="python:3.11-slim",
    namespace="default",
)
```

Airflow uses the in-cluster kubeconfig (or the connection specified by `kubernetes_conn_id`) to authenticate with the cluster.

**Q5. What is `is_delete_operator_pod`?**

`is_delete_operator_pod` (default: `True`) controls whether the Pod is deleted from Kubernetes after it completes. Setting it to `True` keeps the cluster clean. Setting it to `False` lets you `kubectl logs` or `kubectl describe` the completed Pod — useful for debugging failures.

---

## Intermediate

**Q6. How do you pass environment variables and Kubernetes Secrets to a Pod?**

Two separate mechanisms:

**Plain env vars** (non-sensitive config):
```python
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

KubernetesPodOperator(
    task_id="with_env",
    name="env-pod",
    image="myrepo/job:latest",
    namespace="airflow",
    env_vars={"RUN_DATE": "{{ ds }}", "BATCH_SIZE": "100"},
)
```

**Kubernetes Secrets** (sensitive values stored in K8s Secret objects):
```python
from kubernetes.client import V1EnvVar, V1EnvVarSource, V1SecretKeySelector

secret_env = V1EnvVar(
    name="DB_PASSWORD",
    value_from=V1EnvVarSource(
        secret_key_ref=V1SecretKeySelector(name="db-secret", key="password")
    )
)
KubernetesPodOperator(
    task_id="with_secret",
    name="secret-pod",
    image="myrepo/job:latest",
    namespace="airflow",
    env_vars=[secret_env],
)
```

The `secrets` parameter (using `airflow.providers.cncf.kubernetes.secret.Secret`) is the higher-level Airflow abstraction:
```python
from airflow.providers.cncf.kubernetes.secret import Secret

db_secret = Secret("env", "DB_PASSWORD", "db-secret", "password")
KubernetesPodOperator(
    task_id="with_airflow_secret",
    name="secret-pod",
    image="myrepo/job:latest",
    namespace="airflow",
    secrets=[db_secret],
)
```

**Q7. How do you set resource requests and limits?**

Use `container_resources` with a `kubernetes.client.V1ResourceRequirements` object:

```python
from kubernetes.client import V1ResourceRequirements

KubernetesPodOperator(
    task_id="ml_training",
    name="trainer-pod",
    image="myrepo/trainer:latest",
    namespace="ml",
    container_resources=V1ResourceRequirements(
        requests={"cpu": "2", "memory": "4Gi"},
        limits={"cpu": "4", "memory": "8Gi", "nvidia.com/gpu": "1"},
    ),
)
```

Requests are what the scheduler uses for placement; limits are hard caps. Setting both is a best practice — it allows the cluster to schedule efficiently and prevent resource starvation.

**Q8. How do you get output back from the Pod (XCom)?**

Set `do_xcom_push=True`. Airflow creates a sidecar container that reads from a shared volume file `/airflow/xcom/return.json`. Your main container must write its output to that path:

```python
# Inside your container:
import json, pathlib
pathlib.Path("/airflow/xcom/return.json").write_text(json.dumps({"rows": 1234}))
```

```python
KubernetesPodOperator(
    task_id="xcom_pod",
    name="xcom-pod",
    image="myrepo/job:latest",
    namespace="airflow",
    do_xcom_push=True,
)
```

Downstream: `ti.xcom_pull(task_ids="xcom_pod")` returns the dict `{"rows": 1234}`.

**Q9. What does `get_logs=True` do?**

`get_logs=True` (the default) tells Airflow to stream the Pod's stdout/stderr to the Airflow task log in real time. This makes debugging straightforward — you see the container's output directly in the Airflow UI without needing `kubectl logs`. Set `get_logs=False` only if log volume is extremely high and you are sending logs to a separate log aggregation system.

**Q10. How do you use a ConfigMap to mount configuration files into the Pod?**

```python
from kubernetes.client import V1Volume, V1VolumeMount, V1ConfigMapVolumeSource

KubernetesPodOperator(
    task_id="with_config",
    name="config-pod",
    image="myrepo/job:latest",
    namespace="airflow",
    volumes=[
        V1Volume(
            name="app-config",
            config_map=V1ConfigMapVolumeSource(name="my-configmap"),
        )
    ],
    volume_mounts=[
        V1VolumeMount(name="app-config", mount_path="/app/config", read_only=True)
    ],
)
```

The ConfigMap `my-configmap` must already exist in the `airflow` namespace.

---

## Advanced

**Q11. How does pod affinity work and why would you use it?**

Pod affinity (and anti-affinity) tells the Kubernetes scheduler to place (or avoid placing) a Pod near other Pods or on specific nodes. Use cases in data pipelines:

- **Node affinity**: Schedule ML training Pods on GPU nodes.
- **Pod anti-affinity**: Spread independent pipeline Pods across nodes to avoid single-node failure.

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
                            key="accelerator", operator="In", values=["nvidia-gpu"]
                        )
                    ]
                )
            ]
        )
    )
)

KubernetesPodOperator(
    task_id="gpu_training",
    name="gpu-pod",
    image="myrepo/trainer:cuda",
    namespace="ml",
    affinity=gpu_affinity,
)
```

**Q12. What are init containers and when would you use them in KPO?**

Init containers run and complete before the main container starts. Use them to:
- Download model weights or data from S3 before training starts.
- Run database schema migrations before the application starts.
- Wait for a dependency service to become ready.

```python
from kubernetes.client import V1InitContainer

KubernetesPodOperator(
    task_id="with_init",
    name="init-pod",
    image="myrepo/trainer:latest",
    namespace="airflow",
    init_containers=[
        V1InitContainer(
            name="download-data",
            image="amazon/aws-cli:latest",
            command=["aws", "s3", "sync", "s3://my-bucket/data", "/data"],
        )
    ],
)
```

**Q13. Why is KubernetesPodOperator especially well-suited for ML workloads?**

- **GPU access**: Request GPU resources natively via `limits={"nvidia.com/gpu": "1"}`.
- **Large memory**: Cluster nodes can be provisioned with hundreds of GB of RAM, unavailable on a single Airflow worker host.
- **Custom environments**: Each training job uses its own image with pinned library versions — no dependency conflicts.
- **Autoscaling**: Cluster autoscaler can provision new nodes on demand for burst training workloads.
- **Secret management**: Model API keys, database credentials, and cloud credentials live in K8s Secrets — no need to distribute secrets to Airflow workers.
- **Spot/preemptible nodes**: Schedule non-critical batch training on cheaper preemptible instances by using node selectors or tolerations.

**Q14. How does KubernetesPodOperator compare to KubernetesExecutor?**

These solve different problems and are often used together:

| Dimension | KubernetesPodOperator | KubernetesExecutor |
|-----------|----------------------|--------------------|
| What it is | An Airflow task type | An Airflow executor (worker strategy) |
| What it does | Runs a container as a task | Runs each Airflow task in its own Pod (using the Airflow worker image) |
| Custom image per task | Yes — each task has its own image | No — all tasks use the Airflow worker image |
| Control over Pod spec | Full (resources, volumes, affinity) | Limited (set via `executor_config`) |
| When to use | Tasks needing isolated envs, GPUs, non-Python code | When you want workers to scale to zero between runs without custom images |
| Combined use | KubernetesExecutor can run KPO tasks | KPO tasks benefit from KubernetesExecutor's scaling |

**Q15. What are common mistakes when using KubernetesPodOperator?**

1. **Not setting resource limits**: Pods can starve other workloads on the same node.
2. **Using `is_delete_operator_pod=False` in production**: Completed Pods accumulate and consume etcd storage.
3. **Putting secrets in `env_vars` as plain text**: Always use Kubernetes Secrets or Airflow Secrets Backend.
4. **Not setting `get_logs=True`**: Makes debugging task failures much harder.
5. **Using `latest` image tag**: Breaks reproducibility — pin to a specific digest or semver tag.
6. **Not testing XCom file write in the container**: If `/airflow/xcom/return.json` is not written, `do_xcom_push=True` silently pushes `None`.

---

## 📂 Navigation

| | |
|---|---|
| **Parent folder** | [06_All_Operators](../) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Prev operator** | [06_DockerOperator](../06_DockerOperator/) |
| **Next operator** | [08_TriggerDagRunOperator](../08_TriggerDagRunOperator/) |
| **Section root** | [02_Intermediate](../../) |
