# KubernetesPodOperator Deep Dive — Interview Q&A

These questions are common in senior data engineering and platform engineering
interviews where Kubernetes-native Airflow usage is a core topic.

---

## Q1. Describe the full lifecycle of a KubernetesPodOperator task.

**Answer:**
When the Airflow scheduler picks up a KPO task, the following happens:

1. **Pod spec construction**: the operator builds a `V1Pod` spec from its parameters
   (image, resources, volumes, env vars, secrets, etc.).

2. **Pod submission**: the operator calls the Kubernetes API (`POST /api/v1/namespaces/{ns}/pods`)
   to create the pod. This uses the `kubernetes_conn_id` connection (or the in-cluster
   service account if running inside Kubernetes).

3. **Pending phase**: Kubernetes schedules the pod onto a node. The operator logs
   the pod name and watches the pod status.

4. **Container running**: the container starts. If `get_logs=True`, the operator
   streams container stdout/stderr to the Airflow task log via the K8s log API.

5. **Completion**: the main container exits. Kubernetes sets pod phase to `Succeeded`
   or `Failed`.

6. **XCom retrieval** (if `do_xcom_push=True`): before deletion, the operator reads
   `/airflow/xcom/return.json` from the pod's filesystem via a temporary `exec`.

7. **Pod cleanup** (if `is_delete_operator_pod=True`): the operator deletes the pod.
   If False, the pod remains for debugging (terminated pods don't consume compute).

8. **Task outcome**: exit code 0 → Airflow task succeeds. Non-zero → `AirflowException`
   → task fails and retries apply.

---

## Q2. How does XCom work with KubernetesPodOperator?

**Answer:**
KPO uses a **sidecar-less XCom mechanism** for Airflow 2.5+. The container writes
JSON to `/airflow/xcom/return.json` before exiting:

```python
# Inside the container's entrypoint
import json, os
os.makedirs("/airflow/xcom", exist_ok=True)
with open("/airflow/xcom/return.json", "w") as f:
    json.dump({"output_rows": 50000, "path": "s3://bucket/data/"}, f)
```

The operator reads this file via `kubectl exec` (or the API equivalent) after
the container exits, then pushes the value to Airflow's XCom store.

In Airflow 2.x and earlier, a **sidecar container** was used to share the XCom
file. The sidecar pattern required both containers to share an `emptyDir` volume.
The modern approach using `do_xcom_push=True` does not need a sidecar.

**Important**: keep XCom payloads small (<48 KB by default). For large outputs,
write to S3/GCS and push only the path as XCom.

---

## Q3. How do you override the pod template for a KPO task?

**Answer:**
Use `pod_template_file` or `full_pod_spec` for full control:

```python
# Option 1: YAML file
KubernetesPodOperator(
    task_id="custom_pod",
    pod_template_file="/opt/airflow/pod_templates/gpu_template.yaml",
    # Override specific fields on top of the template
    image="my-registry/training:latest",
    container_resources=k8s.V1ResourceRequirements(limits={"nvidia.com/gpu": "2"}),
)

# Option 2: Programmatic V1Pod object
from kubernetes.client.models import V1Pod
pod = V1Pod(...)  # fully constructed pod spec
KubernetesPodOperator(
    task_id="full_spec_pod",
    full_pod_spec=pod,
)
```

Pod templates are useful when different task types have very different requirements
(GPU node with tolerations, high-memory node, etc.) and you want to keep the DAG
code clean.

---

## Q4. What is the difference between KubernetesPodOperator and KubernetesExecutor?

**Answer:**

| Aspect | KubernetesPodOperator | KubernetesExecutor |
|---|---|---|
| Scope | Individual task | All tasks |
| Configuration | Per-operator parameters | Executor-level pod template |
| Custom image | Per-task (any image) | Typically the Airflow image |
| Isolation | Full (separate pod) | Full (separate pod) |
| Use case | Custom containers, GPU, heavy jobs | All tasks need pod isolation |
| Airflow base | Any executor | Replaces CeleryExecutor/LocalExecutor |

**KubernetesExecutor** makes every Airflow task run in its own pod (using the Airflow
worker image by default). **KPO** lets a specific task run any container image
regardless of what executor the cluster uses.

You can combine them: run KubernetesExecutor globally, and use KPO for tasks that
need a different image (e.g., PyTorch, Spark, custom dependencies).

---

## Q5. How do you inject secrets into a KPO task?

**Answer:**
Three patterns, in order of increasing security:

**Pattern 1: Environment variables from a K8s Secret**
```python
from kubernetes.client import models as k8s

KubernetesPodOperator(
    task_id="secret_env",
    image="my-image",
    env_from=[
        k8s.V1EnvFromSource(
            secret_ref=k8s.V1SecretEnvSource(name="my-secret")
        )
    ],
)
```
The container sees the secret's keys as environment variables. Secrets are visible
in `kubectl describe pod` (base64-encoded) and process environment, so this is
the least secure approach.

**Pattern 2: Mounted as files**
```python
KubernetesPodOperator(
    task_id="secret_file",
    image="my-image",
    volumes=[k8s.V1Volume(name="creds", secret=k8s.V1SecretVolumeSource(secret_name="my-secret"))],
    volume_mounts=[k8s.V1VolumeMount(name="creds", mount_path="/secrets", read_only=True)],
)
# Container reads: open("/secrets/password").read()
```

**Pattern 3: Fetch at runtime via SDK**
```python
# Inside the container, at runtime:
import boto3
secret = boto3.client("secretsmanager").get_secret_value(SecretId="my/secret")
```
With IRSA/Workload Identity, no credentials are pre-injected. The container
fetches them from the secrets service at runtime — the most secure approach.

---

## Q6. How do you handle resource quotas when using KPO at scale?

**Answer:**
When many KPO tasks run concurrently, they compete for cluster resources. Strategies:

1. **Airflow Pools**: create a pool (e.g., `heavy_jobs`, size=5) and assign
   resource-intensive KPO tasks to it. This caps concurrent heavy pods regardless
   of task scheduling.

2. **Kubernetes ResourceQuota**: apply a ResourceQuota to the `data-pipelines`
   namespace to cap total CPU/memory consumption:
   ```yaml
   apiVersion: v1
   kind: ResourceQuota
   metadata: { name: pipeline-quota, namespace: data-pipelines }
   spec:
     hard: { requests.cpu: "50", requests.memory: 200Gi, pods: "100" }
   ```

3. **LimitRange**: set default requests/limits so pods without explicit resource
   settings don't over-provision.

4. **Node selectors + node pool sizing**: route different task types to different
   node pools (standard, high-memory, GPU) using `node_selector` and `tolerations`.

---

## Q7. How do you debug a KPO task that fails with `ImagePullBackOff`?

**Answer:**

1. **Check the pod events**:
   ```bash
   kubectl describe pod <pod-name> -n data-pipelines | grep -A 20 Events
   ```
   Common causes: wrong image tag, image doesn't exist, registry requires auth.

2. **Verify the image tag** in your DAG code and confirm it exists in the registry:
   ```bash
   docker manifest inspect my-registry/my-image:1.0.0
   ```

3. **Check `image_pull_secrets`**: if the registry is private, the pod needs an
   `imagePullSecret` Kubernetes secret containing Docker config:
   ```bash
   kubectl create secret docker-registry registry-secret \
     --docker-server=my-registry \
     --docker-username=user \
     --docker-password=pass \
     -n data-pipelines
   ```
   Reference it in KPO: `image_pull_secrets=[k8s.V1LocalObjectReference("registry-secret")]`.

4. **Set `is_delete_operator_pod=False`** temporarily so the pod persists for
   inspection after Airflow marks the task failed.

---

## Q8. How do you run GPU workloads with KPO?

**Answer:**
GPU tasks require:

1. **GPU-enabled node pool**: nodes with GPU hardware (e.g., AWS `p3.2xlarge`,
   GCP `a2-highgpu-1g`).

2. **NVIDIA device plugin**: installed in the cluster (standard in managed K8s).

3. **GPU resource limit in the pod spec**:
   ```python
   container_resources=k8s.V1ResourceRequirements(
       limits={"nvidia.com/gpu": "1"},
       requests={"cpu": "4", "memory": "16Gi"},
   ),
   ```

4. **Node selector** to target GPU nodes:
   ```python
   node_selector={"accelerator": "nvidia-tesla-t4"},
   ```

5. **Toleration** if GPU nodes are tainted:
   ```python
   tolerations=[k8s.V1Toleration(key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")],
   ```

6. **GPU-enabled Docker image**: must include CUDA libraries matching the GPU driver.
   Use official images from `nvcr.io/nvidia/` or build on top of them.

---

## Q9. What happens to the pod if the Airflow scheduler restarts mid-task?

**Answer:**
With `reattach_on_restart=True` (default in modern provider versions), the scheduler
re-attaches to the existing pod and continues monitoring it. The pod name is stored
so the scheduler can find it after restart.

With `reattach_on_restart=False`, the task is marked as failed when the scheduler
restarts, and the pod may be left running as an orphan. The orphan pod still completes
its work but Airflow does not receive the result.

Best practice:
- Use `reattach_on_restart=True`.
- Set `is_delete_operator_pod=True` so completed pods don't accumulate.
- Monitor for orphaned pods with a periodic cleanup job.

---

## Q10. How does KPO differ in Airflow 3 compared to Airflow 2?

**Answer:**
Key changes in Airflow 3:

1. **`airflow.sdk` imports**: all operators move to `airflow.providers.*`. KPO was
   already in providers so the import path is stable.

2. **Asset integration**: KPO tasks can produce Assets (formerly Datasets), enabling
   event-driven downstream pipelines triggered by KPO task completion.

3. **`execute_complete` for deferrable KPO**: the KPO supports the deferrable
   pattern, releasing the Airflow worker slot while the pod runs and resuming
   only when the pod finishes. This significantly reduces worker resource usage
   for long-running pods.

4. **Pod template improvements**: more granular override support and better
   serialisation for dynamic task mapping with KPO.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Parent: Integrations** | [07_Integrations](../Readme.md) |
| **Previous: Great Expectations** | [43_Great_Expectations](../43_Great_Expectations/Theory.md) |
