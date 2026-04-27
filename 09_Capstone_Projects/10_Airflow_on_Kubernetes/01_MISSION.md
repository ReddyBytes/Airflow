# Project 10 — Airflow on Kubernetes

> KubernetesPodOperator + Helm + RBAC | Difficulty: 🔴 Build Yourself | Time: ~8 hours

---

## The Analogy

Running Airflow tasks on a shared machine is like cooking all your dishes in one pan. Ingredients mix, the pan gets dirty between courses, and a fire from one dish ruins everything else. Kubernetes is the professional kitchen where each dish gets its own station, its own cookware, and its own cleanup crew. Once the dish is done, the station disappears.

**KubernetesExecutor** is Airflow's way of running each task in its own ephemeral Kubernetes pod. The pod starts when the task starts, runs the task container in full isolation, and terminates when the task finishes — success or failure. No shared Python environment, no shared memory, no resource contention between tasks. The scheduler is the head chef calling out orders; the Kubernetes cluster is the kitchen responding to each order with a fresh station.

This is the final and most advanced project. You will deploy Airflow itself onto Kubernetes using the official Helm chart, configure the KubernetesExecutor, and write a DAG that uses `KubernetesPodOperator` to run each task in a different container image — demonstrating true isolation.

---

## Mission

1. **Deploy Airflow** onto a local Kubernetes cluster (minikube or kind) using the official Helm chart
2. **Configure KubernetesExecutor** so every task runs as an isolated pod
3. **Write a DAG** with 3 tasks using `KubernetesPodOperator`:
   - `extract`: runs in `python:3.12-slim`, fetches data from an API
   - `transform`: runs in a pandas-enabled image, processes the data
   - `load`: runs in `postgres:15`, upserts to a database
4. **Configure RBAC** — create a ServiceAccount with minimum permissions for Airflow's scheduler
5. **Set up a PersistentVolume** for DAGs and logs storage

---

## Skills You Will Practice

| Skill | Where |
|---|---|
| **Helm chart deployment** | `helm install airflow apache-airflow/airflow` |
| **KubernetesExecutor** | `executor: KubernetesExecutor` in `values.yaml` |
| **KubernetesPodOperator** | One operator per task, each with a different Docker image |
| **Pod template files** | Custom pod spec: resource limits, env vars, tolerations |
| **RBAC** | ServiceAccount + Role + RoleBinding for scheduler |
| **PersistentVolume** | DAG folder and log storage that survives pod restarts |
| **XCom with K8s** | Custom XCom backend or sidecar approach |

---

## Acceptance Criteria

You are done when all 5 of the following commands succeed:

```bash
# 1. Airflow webserver is reachable
curl -s http://localhost:8080/health | jq '.metadatabase.status'
# Expected: "healthy"

# 2. KubernetesExecutor is active
kubectl get pods -n airflow -l component=scheduler
# Expected: 1 pod Running

# 3. DAG runs without errors
kubectl exec -n airflow deployment/airflow-scheduler -- \
  airflow dags trigger k8s_pipeline_dag
kubectl get pods -n airflow --watch
# Expected: 3 short-lived worker pods (extract/transform/load), then terminate

# 4. Task logs are readable after pods terminate
kubectl exec -n airflow deployment/airflow-webserver -- \
  airflow tasks logs k8s_pipeline_dag extract 2024-01-01T00:00:00+00:00
# Expected: task log output (not empty)

# 5. Data was loaded
kubectl exec -it <postgres-pod> -n airflow -- \
  psql -U airflow -c "SELECT COUNT(*) FROM pipeline_output;"
# Expected: count > 0
```

---

## Difficulty: 🔴 Build Yourself

There are no step-by-step instructions. You have:
- 5 acceptance criteria above
- 3 architectural hints below
- A full reference solution in `src/solution.py` and `03_GUIDE.md` — available if you get stuck

**Attempt for at least 2 hours before opening the solution.**

---

## Files in This Project

| File | Purpose |
|---|---|
| `01_MISSION.md` | This file |
| `02_ARCHITECTURE.md` | K8s cluster diagram, executor comparison, RBAC diagram |
| `03_GUIDE.md` | Acceptance criteria + hints + collapsible full solution |
| `src/starter.py` | DAG scaffold with KubernetesPodOperator TODOs |
| `src/solution.py` | Complete DAG + Helm values.yaml reference |
| `04_RECAP.md` | Summary, key concepts, extensions |

---

## 📂 Navigation

⬅️ **Prev:** [09 — Data Warehouse ETL](../09_Data_Warehouse_ETL/01_MISSION.md) &nbsp;&nbsp; ➡️ **This is the final project**

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
