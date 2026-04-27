# ✈️ Airflow — Capstone Projects

> Airflow tutorials show you operators. Projects prove you can orchestrate real systems.

10 pipelines — from your first ETL to a production Airflow cluster on Kubernetes. Each project runs end-to-end with real data, real operators, and real deployment decisions.

---

## How This Series Works

Every project follows the **Mission Briefing Format**:

```
01_MISSION.md      — What you are building and why it matters
02_ARCHITECTURE.md — DAG graph, data flow, system design
03_GUIDE.md        — Step-by-step build with hints and answers
src/starter.py     — Scaffolded DAG to get you started
src/solution.py    — Complete working Airflow DAG
04_RECAP.md        — What you built, what to extend
```

Difficulty progression:

```
🟢 Fully Guided     — Every step: concept → hint → full answer
🟡 Partially Guided — Steps explained, you write the operator logic
🟠 Minimal Hints    — Requirements + one hint per step
🔴 Build Yourself   — Spec + acceptance criteria, solution at end
```

---

## Projects

### Track 1 — ETL Fundamentals

| # | Project | Difficulty | Core Skills |
|---|---------|------------|-------------|
| 01 | [Forex ETL Pipeline](./01_Forex_ETL_Pipeline/01_MISSION.md) | 🟢 Guided | PythonOperator, PostgresHook, BashOperator, scheduling |
| 02 | [Simple File Processing](./02_Simple_File_Processing/01_MISSION.md) | 🟡 Partial | FileSensor, file triggers, transformation tasks, branching |
| 03 | [Data Quality Pipeline](./03_Data_Quality_Pipeline/01_MISSION.md) | 🟡 Partial | SQLCheckOperator, data assertions, alerting on failures |

### Track 2 — Advanced Pipelines

| # | Project | Difficulty | Core Skills |
|---|---------|------------|-------------|
| 04 | [Multi-Source ETL](./04_Multi_Source_ETL/01_MISSION.md) | 🟠 Hints | Dynamic task mapping (expand()), TaskGroup, parallel sources |
| 05 | [ML Training Pipeline](./05_ML_Training_Pipeline/01_MISSION.md) | 🟠 Hints | KubernetesPodOperator, BranchPythonOperator, MLflow |
| 06 | [Event-Driven Asset Pipeline](./06_Event_Driven_Asset_Pipeline/01_MISSION.md) | 🔴 Self | Airflow 3 Assets, producer/consumer DAGs, multi-asset deps |

### Track 3 — Real-World Systems

| # | Project | Difficulty | Core Skills |
|---|---------|------------|-------------|
| 07 | [Stock Price Pipeline (Kafka)](./07_Stock_Price_Pipeline/01_MISSION.md) | 🟢 Guided | KafkaConsumeSensor, PostgresHook, moving averages, Docker Compose |
| 08 | [ML Model Retraining](./08_ML_Retraining_Pipeline/01_MISSION.md) | 🟡 Partial | MLflow autolog, ShortCircuitOperator, model promotion, drift detection |
| 09 | [Data Warehouse ETL](./09_Data_Warehouse_ETL/01_MISSION.md) | 🟠 Hints | Star schema, dynamic mapping, TaskGroups, SCD Type 1, incremental loads |
| 10 | [Airflow on Kubernetes](./10_Airflow_on_Kubernetes/01_MISSION.md) | 🔴 Self | Helm deploy, KubernetesExecutor, KubernetesPodOperator, RBAC |

---

## Learning Paths

**Path A — Airflow Beginner**
```
01 → 02 → 03 → 04
Focus: core operators, hooks, scheduling, data quality
```

**Path B — Data Engineer**
```
01 → 04 → 07 → 09
Focus: real ETL pipelines with Kafka, multi-source, warehouse
```

**Path C — MLOps Engineer**
```
05 → 08
Focus: ML pipelines with branching, MLflow, model promotion
```

**Path D — Platform Engineer**
```
06 → 10
Focus: Airflow 3 Assets + production K8s deployment
```

---

## Prerequisites

| Track | What you need first |
|---|---|
| Track 1 | Airflow installed locally (via Docker), basic Python |
| Track 2 | Track 1 done, Airflow 3 concepts (Assets, dynamic tasks) |
| Track 3 | Intermediate knowledge: Docker Compose, K8s basics, MLflow |

---

## Navigation

| | |
|---|---|
| Back to Airflow | [README.md](../README.md) |
| Beginner Section | [01_Beginner/](../01_Beginner/) |
| Advanced Section | [03_Advanced/](../03_Advanced/) |
| Cloud | [06_Airflow_on_Cloud/](../06_Airflow_on_Cloud/) |
