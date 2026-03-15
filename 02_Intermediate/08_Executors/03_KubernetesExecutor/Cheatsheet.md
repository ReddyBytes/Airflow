# KubernetesExecutor — Cheatsheet

> Quick reference for Apache Airflow 3. One pod per task, no idle workers, cloud-native.

---

## Core Configuration

```ini
# airflow.cfg
[core]
executor = KubernetesExecutor

[kubernetes_executor]
namespace = airflow
worker_container_repository = myrepo/airflow
worker_container_tag = 3.0.0
pod_template_file = /opt/airflow/pod_templates/pod_template.yaml
delete_worker_pods = True
in_cluster = True
```

```bash
# Environment variables
export AIRFLOW__CORE__EXECUTOR=KubernetesExecutor
export AIRFLOW__KUBERNETES_EXECUTOR__NAMESPACE=airflow
export AIRFLOW__KUBERNETES_EXECUTOR__WORKER_CONTAINER_REPOSITORY=myrepo/airflow
export AIRFLOW__KUBERNETES_EXECUTOR__WORKER_CONTAINER_TAG=3.0.0
export AIRFLOW__KUBERNETES_EXECUTOR__POD_TEMPLATE_FILE=/opt/airflow/pod_template.yaml
export AIRFLOW__KUBERNETES_EXECUTOR__DELETE_WORKER_PODS=True
export AIRFLOW__KUBERNETES_EXECUTOR__IN_CLUSTER=True
```

---

## Key Configuration Parameters

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `[core] executor` | `AIRFLOW__CORE__EXECUTOR` | — | Set to `KubernetesExecutor` |
| `[kubernetes_executor] namespace` | `AIRFLOW__KUBERNETES_EXECUTOR__NAMESPACE` | `default` | K8s namespace for task pods |
| `[kubernetes_executor] worker_container_repository` | `AIRFLOW__KUBERNETES_EXECUTOR__WORKER_CONTAINER_REPOSITORY` | — | Docker image repo for worker pods |
| `[kubernetes_executor] worker_container_tag` | `AIRFLOW__KUBERNETES_EXECUTOR__WORKER_CONTAINER_TAG` | — | Docker image tag |
| `[kubernetes_executor] pod_template_file` | `AIRFLOW__KUBERNETES_EXECUTOR__POD_TEMPLATE_FILE` | — | Path to pod template YAML |
| `[kubernetes_executor] delete_worker_pods` | `AIRFLOW__KUBERNETES_EXECUTOR__DELETE_WORKER_PODS` | `True` | Delete pods after completion |
| `[kubernetes_executor] in_cluster` | `AIRFLOW__KUBERNETES_EXECUTOR__IN_CLUSTER` | `True` | Use in-cluster kubeconfig |
| `[kubernetes_executor] multi_namespace_mode` | `AIRFLOW__KUBERNETES_EXECUTOR__MULTI_NAMESPACE_MODE` | `False` | Allow pods in multiple namespaces |

---

## Pod Template Key Concepts

```yaml
# Must-know pod template fields

spec:
  serviceAccountName: airflow-worker    # Must have pod create/delete/list RBAC
  restartPolicy: Never                  # Always Never — Airflow manages retries
  containers:
    - name: base                        # Container MUST be named "base"
      image: myrepo/airflow:3.0.0
      resources:
        requests:                       # Minimum guaranteed resources
          cpu: "500m"
          memory: "512Mi"
        limits:                         # Maximum allowed resources
          cpu: "2"
          memory: "2Gi"
```

---

## Per-Task Resource Override

```python
# Override resources for a specific task only
@task(
    executor_config={
        "pod_override": {
            "spec": {
                "containers": [{
                    "name": "base",
                    "resources": {
                        "requests": {"cpu": "4", "memory": "16Gi"},
                        "limits":   {"cpu": "8", "memory": "32Gi"},
                    }
                }]
            }
        }
    }
)
def heavy_task():
    pass
```

---

## Image Pull Policy Options

| Value | Behaviour |
|---|---|
| `Always` | Pull image on every pod start (slower, always latest) |
| `IfNotPresent` | Use cached image if available (faster, recommended for tagged versions) |
| `Never` | Never pull — image must already exist on the node |

**Production recommendation:** Always use a pinned tag + `IfNotPresent`.

---

## Remote Logging (Required)

```ini
# airflow.cfg — logs vanish when pods terminate without this
[logging]
remote_logging = True
remote_base_log_folder = s3://my-bucket/airflow-logs/
remote_log_conn_id = aws_default
```

---

## When to Use KubernetesExecutor

| Condition | Use KubernetesExecutor? |
|---|---|
| Already running Airflow on Kubernetes | Yes |
| Need per-task container isolation | Yes |
| Tasks have very different resource needs | Yes |
| Want zero idle worker cost | Yes |
| Tasks take < 30 seconds total | No — pod startup overhead dominates |
| No Kubernetes cluster | No — use CeleryExecutor or LocalExecutor |
| Team has no K8s expertise | No — operational complexity is high |
| Need sub-second task scheduling | No — use CeleryExecutor |

---

## Quick Comparison

| | LocalExecutor | CeleryExecutor | KubernetesExecutor |
|---|---|---|---|
| Broker needed | No | Yes | No |
| Idle workers | Yes | Yes | No |
| Startup overhead | < 1s | < 1s | 10–30s |
| Container isolation | No | No | Yes |
| K8s required | No | No | Yes |
| Custom image per task | No | No | Yes (pod override) |

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Prev Executor** | [02_CeleryExecutor](../02_CeleryExecutor/) |
| **Next Executor** | [04_EdgeExecutor](../04_EdgeExecutor/) |
| **Section Root** | [08_Executors](../) |
