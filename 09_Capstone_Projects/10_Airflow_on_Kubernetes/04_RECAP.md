# Project 10 — Recap

---

## What You Built

A Kubernetes-native Airflow deployment where each task runs in its own isolated container. The pipeline fetches data from an API, transforms it with pandas, and writes to Postgres — all without a shared Python environment, without shared memory, and without resource contention.

```
extract (python:3.12-slim pod)
  → transform (python:3.12-slim + pandas pod)
  → load (python:3.12-slim + psycopg2 pod)
```

---

## Key Concepts

### KubernetesExecutor: Ephemeral Workers

With `LocalExecutor` or `CeleryExecutor`, workers are long-running processes that execute tasks sequentially or in parallel. They share a Python environment, share memory, and accumulate state over time.

With `KubernetesExecutor`, there are no long-running workers. The scheduler creates a new pod for each task instance. The pod runs the task, terminates, and is garbage-collected. The next task gets a fresh pod. This means:

- No shared state between tasks (unless you explicitly mount a shared volume)
- No "works on my worker but not yours" bugs
- Resource limits enforced at the pod level, not the worker level
- Natural scaling: more concurrent tasks = more pods, limited only by cluster capacity

The cost is higher latency per task (pod startup: ~5-30s) and more complex log management (logs live in pods that may be deleted before you read them).

### Pod Isolation

Each `KubernetesPodOperator` task runs in a separate pod. You can specify a completely different Docker image for each task. This means:

- The `extract` task can run in `python:3.12-slim` (no pandas, smaller image, faster start)
- The `transform` task can run in a pre-built image with pandas, numpy, and scipy
- The `load` task can run in an image with only psycopg2 (or even `postgres:15` for `psql`)

This is the key architectural advantage: each task has exactly the dependencies it needs, nothing more. No dependency conflicts, no large base images that include every library "just in case."

### XCom in Kubernetes

The standard XCom mechanism relies on the Airflow metadata database. Task pods communicate with this DB via the same network. For most cases this works fine. The exception is when task pods run in a different network namespace or when XCom payloads are large (XCom values are stored in the DB; >1MB becomes a problem).

Solutions in order of complexity:
1. Use Postgres or another shared store directly (this project's approach: write to a staging table)
2. Use a shared PVC mounted to all task pods (file-based handoff)
3. Configure S3 XCom backend (`airflow.providers.amazon.aws.xcom_backends.s3.S3XComBackend`)

### Helm Values: The Right Knobs

The three values.yaml settings that matter most:

| Setting | Effect |
|---|---|
| `executor: KubernetesExecutor` | Switches Airflow from LocalExecutor to K8s |
| `delete_worker_pods: "True"` | Cleans up completed pods (avoids pod accumulation) |
| `delete_worker_pods_on_failure: "False"` | Keeps failed pods for debugging |

Keeping failed pods is critical for debugging production issues. If you delete them immediately, you lose the logs.

### RBAC: Least Privilege

The Airflow scheduler needs exactly three things to manage task pods:
- `create` pods (to start tasks)
- `get` / `list` / `watch` pods (to monitor task status)
- `delete` pods (to clean up)
- `get` pod logs (to collect task logs)

Nothing else. No ClusterRole, no `*` verbs, no cross-namespace access. The `RoleBinding` scopes these permissions to the `airflow` namespace only.

---

## Extend It

**Add KEDA for event-driven scaling**
KEDA (Kubernetes Event-Driven Autoscaling) scales Kubernetes deployments based on external metrics. For Airflow, KEDA can watch the number of queued tasks in the metadata DB and scale the scheduler or trigger additional worker capacity. This eliminates the "first task waits 2 minutes for a pod" startup latency during traffic spikes.

**Use ArgoCD for DAG GitOps**
Instead of manually copying DAG files into pods, use ArgoCD to sync DAG files from a Git repository to the DAG PersistentVolume. Every `git push` to the DAG repository automatically syncs to the Airflow cluster within minutes. This is the production-standard approach for DAG deployment in Kubernetes environments.

**Add Prometheus + Grafana for Airflow metrics**
The official Airflow Helm chart includes a `StatsD` exporter that publishes Airflow metrics to Prometheus. Connect Grafana to Prometheus and build dashboards showing: task success/failure rates, scheduler heartbeat, pool slot utilization, and pod startup latency. Add alerting rules for scheduler lag and task failure spikes.

**Use Spot/Preemptible instances for worker pods**
Since KubernetesExecutor tasks are ephemeral, they are ideal for Spot instances (AWS) or Preemptible VMs (GCP). Add `tolerations` and `nodeAffinity` to the pod template to schedule worker pods on spot nodes only. The scheduler and webserver run on on-demand nodes. This can reduce compute costs by 60-80% for batch workloads.

---

## You Made It

This was the final capstone project. You have built:

| # | Project | Core Skill |
|---|---|---|
| 07 | Stock Price Pipeline | Kafka + sensors + XCom |
| 08 | ML Retraining Pipeline | BranchPythonOperator + MLflow + ShortCircuitOperator |
| 09 | Data Warehouse ETL | Dynamic task mapping + TaskGroups + star schema |
| 10 | Airflow on Kubernetes | KubernetesExecutor + Helm + RBAC + pod isolation |

The progression from guided (07) to build-yourself (10) mirrors the real-world journey from learning Airflow to owning a production deployment.

---

## 📂 Navigation

⬅️ **Prev:** [09 — Data Warehouse ETL](../09_Data_Warehouse_ETL/01_MISSION.md) &nbsp;&nbsp; ➡️ **This is the final project**

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
