# KubernetesExecutor — Code Examples

> Apache Airflow 3. Full working examples for deploying and using KubernetesExecutor.

---

## 1. `airflow.cfg` Configuration

```ini
# airflow.cfg — KubernetesExecutor

[core]
executor = KubernetesExecutor

[database]
sql_alchemy_conn = postgresql+psycopg2://airflow:airflow@postgres:5432/airflow

[kubernetes_executor]
# Namespace where task pods will be created
namespace = airflow

# Docker image for task pods (must contain Airflow + all providers)
worker_container_repository = myrepo/airflow
worker_container_tag = 3.0.0

# Path to the pod template file
pod_template_file = /opt/airflow/pod_templates/pod_template.yaml

# Delete pods after completion — set False only for debugging
delete_worker_pods = True

# In-cluster: True when Airflow runs inside K8s (Helm deployment)
# False: use kubeconfig file (local dev / out-of-cluster)
in_cluster = True

# Seconds to wait for pod to start before marking it failed
start_timeout = 120

# Max number of pods the scheduler will create in a single scheduler loop
max_pods_per_loop = 100

[logging]
# Required — logs are lost when pods terminate without remote storage
remote_logging = True
remote_base_log_folder = s3://my-airflow-logs/
remote_log_conn_id = aws_default
```

---

## 2. Pod Template File with Resource Limits, Env Vars, and Volumes

```yaml
# pod_templates/pod_template.yaml
# This template is applied to ALL task pods.
# Individual tasks can override specific fields via executor_config.

apiVersion: v1
kind: Pod
metadata:
  name: placeholder-name            # Airflow replaces this at runtime
  namespace: airflow
  labels:
    tier: airflow
    component: worker
    app: airflow
spec:
  serviceAccountName: airflow-worker  # Must have pod CRUD RBAC
  restartPolicy: Never                # Always Never for Airflow tasks
  imagePullSecrets:
    - name: registry-credentials      # For private Docker registries

  tolerations:
    - key: "workload"
      operator: "Equal"
      value: "airflow"
      effect: "NoSchedule"

  nodeSelector:
    workload: airflow                  # Schedule only on airflow-labelled nodes

  initContainers:
    - name: git-sync                   # Sync DAG files from Git before task starts
      image: registry.k8s.io/git-sync/git-sync:v4.2.4
      env:
        - name: GITSYNC_REPO
          value: "https://github.com/myorg/airflow-dags.git"
        - name: GITSYNC_BRANCH
          value: "main"
        - name: GITSYNC_ONE_TIME
          value: "true"
        - name: GITSYNC_ROOT
          value: "/dags"
      volumeMounts:
        - name: dags
          mountPath: /dags

  containers:
    - name: base                        # Main container MUST be named "base"
      image: myrepo/airflow:3.0.0
      imagePullPolicy: IfNotPresent
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "2"
          memory: "2Gi"
      env:
        - name: AIRFLOW__CORE__EXECUTOR
          value: KubernetesExecutor
        - name: AIRFLOW__DATABASE__SQL_ALCHEMY_CONN
          valueFrom:
            secretKeyRef:
              name: airflow-secrets
              key: sql-alchemy-conn
        - name: AIRFLOW__CORE__FERNET_KEY
          valueFrom:
            secretKeyRef:
              name: airflow-secrets
              key: fernet-key
        - name: AIRFLOW__LOGGING__REMOTE_LOGGING
          value: "True"
        - name: AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER
          value: "s3://my-airflow-logs/"
        - name: AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID
          value: "aws_default"
      volumeMounts:
        - name: dags
          mountPath: /opt/airflow/dags
          readOnly: true
        - name: airflow-config
          mountPath: /opt/airflow/airflow.cfg
          subPath: airflow.cfg

  volumes:
    - name: dags
      emptyDir: {}                      # Populated by git-sync initContainer
    - name: airflow-config
      configMap:
        name: airflow-config
```

---

## 3. Per-Task Pod Override (Resource Limits + Custom Image)

```python
# dags/kubernetes_executor_demo.py

from airflow.decorators import dag, task
from datetime import datetime


@dag(
    dag_id="kubernetes_executor_demo",
    description="Demonstrates KubernetesExecutor pod overrides",
    schedule="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["executor", "kubernetes"],
)
def kubernetes_executor_demo():

    # Default task — uses pod template defaults
    @task
    def validate_data() -> str:
        print("Quick validation — default 512Mi / 2 CPU pod is fine")
        return "validated"

    # Memory-intensive task — override memory limits
    @task(
        executor_config={
            "pod_override": {
                "spec": {
                    "containers": [
                        {
                            "name": "base",
                            "resources": {
                                "requests": {"cpu": "2", "memory": "8Gi"},
                                "limits":   {"cpu": "4", "memory": "16Gi"},
                            },
                        }
                    ]
                }
            }
        }
    )
    def process_large_dataset(validation_status: str) -> str:
        print(f"Processing large dataset — status: {validation_status}")
        print("This pod has 4 CPU and 16 GB RAM")
        return "processed"

    # GPU task — override with GPU resources and node selector
    @task(
        executor_config={
            "pod_override": {
                "spec": {
                    "nodeSelector": {"accelerator": "nvidia-v100"},
                    "tolerations": [
                        {
                            "key": "nvidia.com/gpu",
                            "operator": "Exists",
                            "effect": "NoSchedule",
                        }
                    ],
                    "containers": [
                        {
                            "name": "base",
                            "resources": {
                                "requests": {
                                    "cpu": "4",
                                    "memory": "32Gi",
                                    "nvidia.com/gpu": "1",
                                },
                                "limits": {
                                    "cpu": "8",
                                    "memory": "64Gi",
                                    "nvidia.com/gpu": "1",
                                },
                            },
                        }
                    ],
                }
            }
        }
    )
    def train_ml_model(processed_data: str) -> str:
        print(f"Training ML model on data: {processed_data}")
        print("This pod runs on a GPU node with 64 GB RAM")
        return "model_v1"

    # Final task — default resources are fine for uploading a model artifact
    @task
    def upload_model(model_version: str) -> None:
        print(f"Uploading model {model_version} to model registry")

    status = validate_data()
    data = process_large_dataset(status)
    model = train_ml_model(data)
    upload_model(model)


kubernetes_executor_demo()
```

---

## 4. Full Helm `values.yaml` Snippet for KubernetesExecutor

```yaml
# values.yaml — key sections for official apache-airflow Helm chart

executor: "KubernetesExecutor"

images:
  airflow:
    repository: myrepo/airflow
    tag: "3.0.0"
    pullPolicy: IfNotPresent

config:
  core:
    executor: KubernetesExecutor
  kubernetes_executor:
    namespace: airflow
    delete_worker_pods: "True"
    worker_container_repository: myrepo/airflow
    worker_container_tag: "3.0.0"
    pod_template_file: /opt/airflow/pod_templates/pod_template.yaml
  logging:
    remote_logging: "True"
    remote_base_log_folder: "s3://my-airflow-logs/"
    remote_log_conn_id: "aws_default"

# DAG sync via Git
dags:
  gitSync:
    enabled: true
    repo: https://github.com/myorg/airflow-dags.git
    branch: main
    rev: HEAD
    depth: 1
    maxFailures: 0
    subPath: "dags"
    period: 60s   # Sync every 60 seconds

# Pod template for task pods
workers:
  podAnnotations: {}
  resources:
    requests:
      memory: "512Mi"
      cpu: "500m"
    limits:
      memory: "2Gi"
      cpu: "2"
  tolerations:
    - key: "workload"
      operator: "Equal"
      value: "airflow"
      effect: "NoSchedule"
  nodeSelector:
    workload: airflow

# Scheduler settings
scheduler:
  replicas: 1
  resources:
    requests:
      memory: "2Gi"
      cpu: "1"
    limits:
      memory: "4Gi"
      cpu: "2"
```

---

## 5. RBAC Setup for Airflow Worker Service Account

```yaml
# kubernetes/airflow-rbac.yaml

apiVersion: v1
kind: ServiceAccount
metadata:
  name: airflow-worker
  namespace: airflow

---

apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: airflow-worker-role
  namespace: airflow
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["create", "get", "list", "watch", "delete", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create", "get"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list"]

---

apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: airflow-worker-rolebinding
  namespace: airflow
subjects:
  - kind: ServiceAccount
    name: airflow-worker
    namespace: airflow
roleRef:
  kind: Role
  name: airflow-worker-role
  apiGroup: rbac.authorization.k8s.io
```

```bash
# Apply RBAC
kubectl apply -f kubernetes/airflow-rbac.yaml

# Verify the service account exists
kubectl get serviceaccount airflow-worker -n airflow

# Verify permissions (test if the scheduler can create pods)
kubectl auth can-i create pods --as=system:serviceaccount:airflow:airflow-worker -n airflow
# Expected: yes
```

---

## 6. Debugging a Failed Task Pod

```bash
# List recent task pods (failed pods remain if delete_worker_pods=False)
kubectl get pods -n airflow --sort-by=.metadata.creationTimestamp | tail -20

# Describe a failed pod (look at Events section for OOMKill or image pull errors)
kubectl describe pod <pod-name> -n airflow

# Get logs from a failed pod
kubectl logs <pod-name> -n airflow

# Get logs from a previous pod attempt (if the pod restarted)
kubectl logs <pod-name> -n airflow --previous

# Exec into a running pod for live debugging
kubectl exec -it <pod-name> -n airflow -- /bin/bash
```

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Interview Q&A** | [Interview_QA.md](./Interview_QA.md) |
| **Prev Executor** | [02_CeleryExecutor](../02_CeleryExecutor/) |
| **Next Executor** | [04_EdgeExecutor](../04_EdgeExecutor/) |
| **Section Root** | [08_Executors](../) |
