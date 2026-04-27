# Project 10 — Architecture

---

## Kubernetes Cluster Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         KUBERNETES CLUSTER (minikube/kind)                   │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                         NAMESPACE: airflow                             │  │
│  │                                                                        │  │
│  │  ┌─────────────────────┐    ┌─────────────────────┐                   │  │
│  │  │  airflow-webserver  │    │  airflow-scheduler  │                   │  │
│  │  │  (Deployment)       │    │  (Deployment)       │◀── Helm chart     │  │
│  │  │  port: 8080         │    │  KubernetesExecutor │                   │  │
│  │  └─────────────────────┘    └──────────┬──────────┘                   │  │
│  │                                        │ creates pods per task        │  │
│  │  ┌─────────────────────┐               │                              │  │
│  │  │  airflow-postgresql  │               ▼                              │  │
│  │  │  (StatefulSet)       │    ┌──────────────────────┐                 │  │
│  │  │  metadata DB         │    │  Worker Pod          │ (ephemeral)     │  │
│  │  └─────────────────────┘    │  task_id: extract    │                 │  │
│  │                              │  image: python:3.12  │                 │  │
│  │  ┌─────────────────────┐    │  status: Running...  │                 │  │
│  │  │  airflow-redis       │    │  → Completed         │                 │  │
│  │  │  (only for Celery)   │    │  → Terminated ✓      │                 │  │
│  │  │  NOT needed for K8s  │    └──────────────────────┘                 │  │
│  │  └─────────────────────┘                                              │  │
│  │                              (New pod for each task, then gone)       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │  PersistentVolumeClaim: airflow-dags  (ReadWriteMany)           │  │  │
│  │  │  Mounted at: /opt/airflow/dags  in scheduler + webserver pods   │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## KubernetesPodOperator Lifecycle

```
DAG run triggered
       │
       ▼
Scheduler reads DAG, identifies KubernetesPodOperator task
       │
       ▼
Scheduler calls Kubernetes API:
    POST /api/v1/namespaces/airflow/pods
    spec: {image, command, env, resources, serviceAccountName}
       │
       ▼
Kubernetes schedules pod on a worker node
       │
       ▼
Container image pulled (if not cached)
       │
       ▼
Container runs task command
       │
    ┌──┴──────────────────────────────────┐
    │ Succeeded?                          │ Failed?
    ▼                                     ▼
Pod status: Completed               Pod status: Failed
Scheduler: task = SUCCESS           Scheduler: task = FAILED
    │                                     │
    ▼                                     ▼
Pod terminated                      Pod logs captured
(garbage collected by K8s)          Pod terminated
```

---

## RBAC Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                     K8s RBAC Configuration                        │
│                                                                   │
│  ServiceAccount: airflow-scheduler                                │
│  Namespace: airflow                                               │
│                                                                   │
│  Role: airflow-pod-manager                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ apiGroups: [""]                                             │  │
│  │ resources: ["pods", "pods/log"]                             │  │
│  │ verbs: ["get", "list", "watch", "create", "delete", "patch"]│  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  RoleBinding: airflow-scheduler-binding                           │
│  Binds ServiceAccount → Role (scoped to namespace: airflow)       │
│                                                                   │
│  Why NOT ClusterRole?                                             │
│  Least-privilege: scheduler only needs to manage pods in its      │
│  own namespace. A ClusterRole grants access to ALL namespaces.    │
└───────────────────────────────────────────────────────────────────┘
```

---

## Executor Comparison

```
┌────────────────────┬───────────────────┬──────────────────┬────────────────────┐
│ Feature            │ LocalExecutor     │ CeleryExecutor   │ KubernetesExecutor │
├────────────────────┼───────────────────┼──────────────────┼────────────────────┤
│ Isolation          │ None (same proc)  │ Worker process   │ Full pod           │
│ Dependency mgmt    │ Shared env        │ Shared env       │ Per-task image     │
│ Scaling            │ Single machine    │ Add workers      │ Elastic (K8s)      │
│ Resource limits    │ None              │ Per worker       │ Per task           │
│ Setup complexity   │ Low               │ Medium           │ High               │
│ Log persistence    │ Local disk        │ Worker disk      │ Needs PVC/S3       │
│ Cost               │ Fixed             │ Fixed (workers)  │ Pay-per-task       │
│ Use case           │ Dev/small teams   │ High parallelism │ Mixed workloads    │
└────────────────────┴───────────────────┴──────────────────┴────────────────────┘
```

---

## Helm Chart Values Structure

```yaml
# values.yaml — key sections

executor: "KubernetesExecutor"   # ← the critical setting

# Airflow configuration
config:
  core:
    executor: KubernetesExecutor
  kubernetes:
    namespace: airflow           # where worker pods are created
    worker_container_repository: apache/airflow
    worker_container_tag: 2.8.0

# Webserver
webserver:
  replicas: 1
  service:
    type: NodePort
    nodePort: 30080

# Scheduler
scheduler:
  replicas: 1
  serviceAccount:
    create: true
    name: airflow-scheduler

# Persistent Volume for DAGs
dags:
  persistence:
    enabled: true
    size: 1Gi
    accessMode: ReadWriteMany   # ← both scheduler and webserver must read DAGs

# Persistent Volume for logs
logs:
  persistence:
    enabled: true
    size: 5Gi
```

---

## PV/PVC for DAGs

```
PersistentVolume (cluster admin creates this)
    hostPath: /data/airflow-dags   ← on minikube node
    accessModes: [ReadWriteMany]
    capacity: 1Gi
         │
         │  bound to
         ▼
PersistentVolumeClaim (Helm chart creates this)
    name: airflow-dags
    namespace: airflow
    storageClassName: standard
         │
         │  mounted at
         ├──▶ /opt/airflow/dags  in scheduler pod
         └──▶ /opt/airflow/dags  in webserver pod
```

To sync DAG files onto the PV:
```bash
# Copy DAG files into the minikube node's hostPath
minikube ssh "mkdir -p /data/airflow-dags"
kubectl cp src/solution.py airflow/$(kubectl get pod -n airflow -l component=scheduler \
  -o jsonpath='{.items[0].metadata.name}'):/opt/airflow/dags/k8s_pipeline_dag.py
```

---

## 📂 Navigation

⬅️ **Prev:** [09 — Data Warehouse ETL](../09_Data_Warehouse_ETL/01_MISSION.md) &nbsp;&nbsp; ➡️ **This is the final project**

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
