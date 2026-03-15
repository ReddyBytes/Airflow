# Executors — Cheatsheet

## Quick Comparison

| Executor | Parallelism | Infrastructure | Best For |
|----------|------------|---------------|----------|
| SequentialExecutor | 1 task at a time | None | Dev/testing |
| LocalExecutor | Multiple (same machine) | Just a DB | Small prod |
| CeleryExecutor | Many (multi-machine) | Redis + workers | Large prod |
| KubernetesExecutor | Many (pods) | K8s cluster | Enterprise |
| EdgeExecutor | Remote devices | Edge nodes | IoT/edge |

---

## Configuration

```bash
# airflow.cfg
executor = LocalExecutor          # or CeleryExecutor, KubernetesExecutor

# Environment variable
AIRFLOW__CORE__EXECUTOR=CeleryExecutor
```

---

## Parallelism Settings

```ini
[core]
parallelism = 32                  # Max tasks running across all DAGs
max_active_tasks_per_dag = 16     # Max parallel tasks in one DAG
max_active_runs_per_dag = 16      # Max concurrent DAG runs
```

---

## When to Use Each

### ✅ SequentialExecutor
- Local development and quick testing
- Running `airflow standalone`
- Default; no config needed

### ✅ LocalExecutor
- Single production machine
- ≤ ~30 parallel tasks
- No Redis/RabbitMQ available
- Simplest production setup

### ✅ CeleryExecutor
- Multiple worker machines needed
- High parallelism (50+ tasks)
- Need to scale workers independently
- Requires: Redis or RabbitMQ + result backend

### ✅ KubernetesExecutor
- Task isolation is critical (ML, data processing)
- Dynamic resource allocation per task
- Already on Kubernetes
- Pod startup overhead acceptable (~10–30s)

### ✅ EdgeExecutor
- Running tasks at remote locations
- IoT sensors, edge ML inference
- Low-bandwidth environments

---

## Golden Rules

1. Never use SequentialExecutor in production.
2. Start with LocalExecutor — upgrade to Celery only when you need multi-machine scale.
3. KubernetesExecutor shines for ML workloads where each task needs different resources.
4. The executor is swappable — your DAGs don't change when you switch executors.
5. CeleryExecutor needs a broker (Redis/RabbitMQ) AND a result backend (Postgres/Redis).

---

## 📂 Navigation

| File | |
|---|---|
| 📖 **Theory.md** | Executor overview |
| ⚡ **Cheatsheet.md** | ← you are here |
| 📁 [01_LocalExecutor/](./01_LocalExecutor/Theory.md) | LocalExecutor deep dive |
| 📁 [02_CeleryExecutor/](./02_CeleryExecutor/Theory.md) | CeleryExecutor deep dive |
| 📁 [03_KubernetesExecutor/](./03_KubernetesExecutor/Theory.md) | KubernetesExecutor deep dive |
| 📁 [04_EdgeExecutor/](./04_EdgeExecutor/Theory.md) | EdgeExecutor deep dive |

⬅️ **Prev:** [Sensors](../07_Sensors/Theory.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [LocalExecutor](./01_LocalExecutor/Theory.md)
