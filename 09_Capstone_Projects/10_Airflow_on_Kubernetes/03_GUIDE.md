# Project 10 — Build Yourself Guide

> Difficulty: 🔴 Build Yourself.
> 5 acceptance criteria. 3 architectural hints. Full solution available in collapsible section.
> Spend at least 2 hours building before expanding the solution.

---

## Your Mission

Deploy Airflow on Kubernetes and build a DAG that runs each task in an isolated container. The pipeline must pass all 5 acceptance criteria from `01_MISSION.md`.

---

## Acceptance Criteria (repeat for reference)

```bash
# AC1: Airflow webserver is healthy
curl -s http://localhost:8080/health | jq '.metadatabase.status'
# Expected: "healthy"

# AC2: Scheduler pod is running with KubernetesExecutor
kubectl get pods -n airflow -l component=scheduler
# Expected: 1 pod in Running state

# AC3: DAG triggers 3 ephemeral worker pods
kubectl exec -n airflow deployment/airflow-scheduler -- \
  airflow dags trigger k8s_pipeline_dag
kubectl get pods -n airflow --watch
# Expected: pods named "k8s-pipeline-*" appear, run, then terminate

# AC4: Logs readable after pod termination
kubectl exec -n airflow deployment/airflow-webserver -- \
  airflow tasks logs k8s_pipeline_dag extract 2024-01-01T00:00:00+00:00
# Expected: actual log output, not empty

# AC5: Data loaded into Postgres
kubectl exec -it <postgres-pod> -n airflow -- \
  psql -U airflow -c "SELECT COUNT(*) FROM pipeline_output;"
# Expected: count > 0
```

---

## Architectural Hints

### Hint 1 — Helm values for KubernetesExecutor

The most common mistake is deploying Airflow with CeleryExecutor (the default) and wondering why no worker pods appear. The single most important line in your `values.yaml`:

```yaml
executor: "KubernetesExecutor"
```

You also need to configure where worker pods are created:

```yaml
config:
  kubernetes:
    namespace: airflow
    worker_container_repository: apache/airflow
    worker_container_tag: "2.8.0"
    delete_worker_pods: "True"    # ← clean up completed pods automatically
    delete_worker_pods_on_failure: "False"  # ← keep failed pods for debugging
```

---

### Hint 2 — Minimum RBAC permissions for the scheduler

The scheduler needs to create, get, list, watch, and delete pods. It also needs to read pod logs. Nothing else. Apply this before `helm install`:

```yaml
# rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: airflow-scheduler
  namespace: airflow
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: airflow-pod-manager
  namespace: airflow
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log"]
    verbs: ["get", "list", "watch", "create", "delete", "patch", "update"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: airflow-scheduler-binding
  namespace: airflow
subjects:
  - kind: ServiceAccount
    name: airflow-scheduler
    namespace: airflow
roleRef:
  kind: Role
  apiGroup: rbac.authorization.k8s.io
  name: airflow-pod-manager
```

```bash
kubectl apply -f rbac.yaml
```

---

### Hint 3 — XCom backend for Kubernetes

The default XCom backend stores values in the Airflow metadata database. This works fine for `PythonOperator` tasks (the task process is on the scheduler's host). For `KubernetesPodOperator`, the task runs in a separate pod — it cannot write to the metadata DB directly.

Two options:

**Option A (simple): Sidecar approach**
Pass data between KubernetesPodOperator tasks via a shared volume (EmptyDir or PVC). Mount the same PVC in all task pods. Write output to a file; the next task reads it. No XCom needed.

**Option B (recommended): S3 XCom backend**
Configure Airflow to use S3 as the XCom backend:
```yaml
# values.yaml
config:
  core:
    xcom_backend: "airflow.providers.amazon.aws.xcom_backends.s3.S3XComBackend"
  aws_xcom_backend:
    bucket_name: "my-airflow-xcom"
    key_prefix: "xcom/"
```

For local dev (no S3), use the sidecar/shared volume approach.

---

## Quick-Start Commands

```bash
# 1. Start minikube
minikube start --cpus 4 --memory 8192 --driver docker

# 2. Create namespace
kubectl create namespace airflow

# 3. Apply RBAC
kubectl apply -f rbac.yaml

# 4. Add Helm repo
helm repo add apache-airflow https://airflow.apache.org
helm repo update

# 5. Deploy Airflow
helm install airflow apache-airflow/airflow \
  --namespace airflow \
  --values values.yaml \
  --wait

# 6. Port-forward webserver
kubectl port-forward svc/airflow-webserver 8080:8080 --namespace airflow &

# 7. Copy DAG to scheduler pod
kubectl cp src/solution.py \
  airflow/$(kubectl get pod -n airflow -l component=scheduler \
  -o jsonpath='{.items[0].metadata.name}'):/opt/airflow/dags/k8s_pipeline_dag.py

# 8. Trigger the DAG
kubectl exec -n airflow deployment/airflow-scheduler -- \
  airflow dags trigger k8s_pipeline_dag

# 9. Watch pods
kubectl get pods -n airflow --watch
```

---

<details>
<summary>✅ Full Solution — expand only after 2 hours of genuine attempt</summary>

### values.yaml

```yaml
executor: "KubernetesExecutor"

webserver:
  replicas: 1
  service:
    type: NodePort
    nodePort: 30080
  defaultUser:
    enabled: true
    role: Admin
    username: admin
    email: admin@example.com
    firstName: Admin
    lastName: User
    password: admin

scheduler:
  replicas: 1
  serviceAccount:
    create: false
    name: airflow-scheduler

config:
  core:
    executor: KubernetesExecutor
    dags_are_paused_at_creation: "false"
  kubernetes:
    namespace: airflow
    worker_container_repository: apache/airflow
    worker_container_tag: "2.8.0"
    delete_worker_pods: "True"
    delete_worker_pods_on_failure: "False"
    worker_pods_creation_batch_size: "4"

dags:
  persistence:
    enabled: true
    size: 1Gi
    accessMode: ReadWriteMany
    storageClassName: standard

logs:
  persistence:
    enabled: true
    size: 5Gi
    storageClassName: standard

postgresql:
  enabled: true
  auth:
    username: airflow
    password: airflow
    database: airflow
```

### Complete DAG — see `src/solution.py`

The solution DAG uses:
- 3 `KubernetesPodOperator` tasks with different images
- A shared `pod_template_file` for resource limits
- Environment variables injected from a Kubernetes Secret
- Logs written to the PVC so they survive pod termination

</details>

---

## 📂 Navigation

⬅️ **Prev:** [09 — Data Warehouse ETL](../09_Data_Warehouse_ETL/01_MISSION.md) &nbsp;&nbsp; ➡️ **This is the final project**

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
