# KubernetesExecutor — Interview Q&A

> Study guide for Apache Airflow 3. Story-first, beginner-friendly.

---

## Q1: How does KubernetesExecutor map tasks to Kubernetes pods?

**Answer:**

The mapping is one-to-one: **every Airflow task instance gets its own Kubernetes pod**.

When the scheduler detects a task in `scheduled` state, it builds a pod spec using the pod template file (with any task-specific overrides applied) and submits it to the Kubernetes API server via `POST /api/v1/namespaces/{namespace}/pods`.

Kubernetes then schedules the pod on an available node. The pod's container runs `airflow tasks run <dag_id> <task_id> <execution_date>`, which executes the operator's `execute()` method. When the task finishes (success or failure), the pod exits with the appropriate exit code, Airflow records the result in the metadata database, and the pod is deleted (if `delete_worker_pods=True`).

---

## Q2: What is the pod startup overhead of KubernetesExecutor and why does it matter?

**Answer:**

Creating and scheduling a new Kubernetes pod typically takes **10–30 seconds** before the task itself begins executing. This overhead comes from:

1. The scheduler calling the Kubernetes API to create the pod (~1–2 seconds)
2. Kubernetes scheduling the pod to a node (~1–5 seconds)
3. The node pulling the Docker image (0–20+ seconds, skipped if already cached with `IfNotPresent`)
4. The container initialising the Python runtime and Airflow imports (~5–10 seconds)

This overhead matters because:
- For tasks that take 2 minutes, 20 seconds of startup is a 15% overhead — acceptable.
- For tasks that take 5 seconds, 20 seconds of startup is 400% overhead — not acceptable.
- For DAGs with hundreds of very short tasks, startup overhead compounds and significantly slows throughput.

**When startup overhead is a problem**, use CeleryExecutor (workers are persistent, startup < 1 second) or combine executors with `CeleryKubernetesExecutor`.

---

## Q3: How do you customise the pod spec for all tasks? How do you customise it for a specific task?

**Answer:**

**For all tasks** — use the **pod template file**:

```yaml
# pod_template.yaml — applies to all task pods by default
spec:
  serviceAccountName: airflow-worker
  containers:
    - name: base
      image: myrepo/airflow:3.0.0
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "2"
          memory: "2Gi"
```

Configure the path in `airflow.cfg`:
```ini
[kubernetes_executor]
pod_template_file = /opt/airflow/pod_template.yaml
```

**For a specific task** — use `executor_config` with `pod_override` in the operator:

```python
@task(
    executor_config={
        "pod_override": {
            "spec": {
                "containers": [{
                    "name": "base",
                    "resources": {
                        "requests": {"cpu": "4", "memory": "16Gi"},
                        "limits": {"cpu": "8", "memory": "32Gi"},
                    }
                }]
            }
        }
    }
)
def heavy_ml_training():
    pass
```

The `pod_override` is a partial pod spec that is merged on top of the base template.

---

## Q4: How do you set CPU and memory limits for task pods?

**Answer:**

Resource limits are set in the pod template file (for all tasks) or via `executor_config` (per task).

```yaml
# In pod_template.yaml
containers:
  - name: base
    resources:
      requests:         # Minimum guaranteed resources — K8s uses this for scheduling
        cpu: "500m"     # 0.5 CPU core
        memory: "512Mi"
      limits:           # Hard cap — task is OOMKilled if it exceeds memory limit
        cpu: "2"        # 2 CPU cores
        memory: "2Gi"
```

Key concepts:
- **requests**: the minimum resources Kubernetes guarantees for the pod. Used for scheduling decisions. The task is always guaranteed at least this much.
- **limits**: the hard cap. If a task uses more memory than the limit, the container is killed (`OOMKilled`). CPU limits cause throttling, not killing.
- `500m` = 500 millicores = 0.5 CPU. `1` = 1 CPU core. `2` = 2 CPU cores.

Always set both requests and limits. Without them, Kubernetes cannot make intelligent scheduling decisions, and a runaway task can starve other pods on the same node.

---

## Q5: How does KubernetesExecutor differ from KubernetesPodOperator?

**Answer:**

This is a very common interview question and they are completely different:

| Aspect | KubernetesExecutor | KubernetesPodOperator |
|---|---|---|
| **What it is** | An executor (how Airflow runs ALL tasks) | An operator (one specific type of task) |
| **Scope** | Affects every task in every DAG | Only the task using this operator |
| **Image** | Uses the Airflow worker image | Can use any Docker image |
| **Configuration** | In `airflow.cfg` / `[kubernetes_executor]` | In the operator parameters |
| **Use case** | Run Airflow itself on Kubernetes natively | Run a specific containerised job as a task |

You can (and often do) use both together: run Airflow with KubernetesExecutor (all tasks get pods), and within those tasks, some use `KubernetesPodOperator` to launch additional pods with custom images for their actual workload.

---

## Q6: What is in-cluster vs out-of-cluster configuration?

**Answer:**

This refers to how the Airflow scheduler authenticates with the Kubernetes API:

**In-cluster** (`in_cluster = True`):
- Airflow is running **inside** the Kubernetes cluster (as a pod itself — typical for production deployments via Helm).
- Kubernetes automatically provides a service account token and the API server address to pods via environment variables.
- No kubeconfig file needed — Airflow uses the mounted service account credentials.

**Out-of-cluster** (`in_cluster = False`):
- Airflow is running **outside** the Kubernetes cluster (e.g., on a VM, in Docker Compose, or a developer's laptop).
- Airflow reads a kubeconfig file (usually `~/.kube/config`) to get credentials and the API server URL.
- Useful for development, testing, or hybrid setups.

```ini
# In-cluster (Airflow deployed inside K8s — typical production)
[kubernetes_executor]
in_cluster = True

# Out-of-cluster (Airflow on a VM connecting to a remote K8s cluster)
[kubernetes_executor]
in_cluster = False
config_file = /home/airflow/.kube/config
```

---

## Q7: How does Airflow handle task retries with KubernetesExecutor?

**Answer:**

With `retries=3` on a task:

1. Task attempt 1 runs in Pod 1. Pod exits with non-zero code → task marked FAILED.
2. Airflow deletes Pod 1 (if `delete_worker_pods=True`).
3. Airflow waits `retry_delay` seconds, then creates Pod 2 for attempt 2.
4. This repeats up to `retries` times.

Each retry is a **fresh pod**. There is no shared state from the previous attempt — the retry starts with a clean container. This is actually an advantage: transient failures (network blip, memory spike) are automatically recovered with a clean slate.

The `try_number` is passed to the task context so you can access it inside `execute()` if needed.

---

## Q8: How do you handle DAG file distribution with KubernetesExecutor?

**Answer:**

Every task pod needs access to the DAG files to execute. Common distribution patterns:

1. **Persistent Volume Claim (PVC)**: mount the same NFS/EFS PVC on both the scheduler and all task pods. DAG updates are immediately available. Simple but adds a network storage dependency.

2. **Git sync sidecar**: a sidecar container in each pod pulls DAG files from a Git repo on startup. Works well with Helm charts (the official Airflow Helm chart supports this natively with `dags.gitSync`).

3. **Bake DAGs into the image**: include the `dags/` folder in the Docker image. Every code change requires rebuilding and redeploying the image. Guarantees consistency but slower iteration cycle.

4. **Object storage**: a sidecar or init container downloads DAG files from S3/GCS on pod startup.

The **Git sync** approach is the most commonly used with the official Airflow Helm chart.

---

## Q9: What service account permissions does KubernetesExecutor require?

**Answer:**

The Airflow scheduler needs a Kubernetes service account with RBAC permissions to manage pods in the target namespace:

```yaml
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["create", "get", "list", "watch", "delete", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get", "list"]
```

These permissions allow the scheduler to:
- `create`: submit new task pods
- `get`, `list`, `watch`: monitor pod status to detect when tasks complete
- `delete`: clean up pods after tasks finish
- `pods/log`: fetch logs from pods for display in the Airflow UI

If the scheduler lacks these permissions, tasks will fail with `Forbidden` errors from the Kubernetes API.

---

## Q10: How does KubernetesExecutor compare to CeleryExecutor for a high-throughput pipeline?

**Answer:**

For **high-throughput pipelines** (many short tasks, e.g., 1000 tasks/hour each taking 10 seconds):

**CeleryExecutor wins** because:
- Workers are persistent — no 10–30 second pod startup per task
- Task dispatch via Redis is sub-second
- Workers handle many tasks per minute without per-task infrastructure overhead

**KubernetesExecutor struggles** because:
- 1000 tasks/hour means ~17 pod creates/minute. Pod startup overhead dominates for short tasks.
- High pod churn puts load on the Kubernetes API server.
- The scheduler's Kubernetes pod creation loop can become a bottleneck.

**KubernetesExecutor wins** for:
- Tasks with heterogeneous resource needs (one needs 32 GB RAM, another needs 500 MB)
- Tasks requiring different Python environments or Docker images
- Long-running tasks (minutes to hours) where startup overhead is negligible
- Teams that want zero idle worker cost with cluster autoscaling

For mixed workloads, consider `CeleryKubernetesExecutor`.

---

## Q11: What is `delete_worker_pods` and when would you set it to False?

**Answer:**

`delete_worker_pods = True` (default): Airflow deletes the task pod after it completes (success or failure). This keeps the cluster clean and prevents pod accumulation.

`delete_worker_pods = False`: Airflow leaves the pod running (in `Completed` or `Error` state) after the task finishes.

When to set `False`:
- **Debugging failures**: you can `kubectl describe pod <pod-name>` or `kubectl logs <pod-name>` to inspect the pod's state, events, and logs after the task fails.
- **Investigating OOMKills**: the pod's events will show if it was killed due to memory limits.

**Important**: never leave `delete_worker_pods=False` in production long-term — completed pods accumulate and waste namespace resources. Turn it off temporarily for debugging, then restore it.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Prev Executor** | [02_CeleryExecutor](../02_CeleryExecutor/) |
| **Next Executor** | [04_EdgeExecutor](../04_EdgeExecutor/) |
| **Section Root** | [08_Executors](../) |
