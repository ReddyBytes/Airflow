# LocalExecutor in Apache Airflow 3

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [EdgeExecutor](../04_EdgeExecutor/Theory.md)**

---

## The Story: Your First Step Into Real Parallelism

You have been running Airflow with the default `SequentialExecutor` in development. It works fine for testing — tasks run one at a time. But you notice your pipeline takes 45 minutes even though most of that time is tasks waiting on each other unnecessarily. Five tasks that could run at the same time are queued up and running sequentially because the executor only supports one task at a time.

It's time to switch to `LocalExecutor`.

LocalExecutor runs multiple tasks in parallel using Python's `multiprocessing` module. Each task gets its own subprocess. Your 5 independent tasks now truly run at the same time, and your 45-minute pipeline becomes a 12-minute pipeline — without adding any new infrastructure. No Redis. No Celery. No new worker machines. Just configuration.

This is the right executor for small-to-medium production workloads where everything runs on a single machine.

---

## What Is LocalExecutor?

`LocalExecutor` runs task instances in **separate subprocesses** on the same machine as the Airflow scheduler. It is built into Airflow — no provider package required.

Key characteristics:
- **Parallel task execution**: multiple tasks run simultaneously, up to `parallelism` limit
- **Same machine as scheduler**: no separate worker processes, no message broker
- **Simple setup**: change one config line, restart Airflow
- **Subprocess isolation**: each task runs in its own process, so crashes in one task do not affect others
- **Resource sharing**: all tasks share the same machine's CPU and RAM

---

## Configuration

### Setting the Executor

In `airflow.cfg`:
```ini
[core]
executor = LocalExecutor
```

Via environment variable:
```bash
export AIRFLOW__CORE__EXECUTOR=LocalExecutor
```

In Docker Compose or Helm (common deployment patterns):
```yaml
# docker-compose override
environment:
  AIRFLOW__CORE__EXECUTOR: LocalExecutor
```

### Parallelism Settings

| Config Key | Default | Description |
|---|---|---|
| `[core] parallelism` | `32` | Max total tasks running simultaneously across all DAGs |
| `[core] dag_concurrency` | `16` | Max tasks per DAG running simultaneously (Airflow 2.x name) |
| `[core] max_active_tasks_per_dag` | `16` | Same as dag_concurrency (Airflow 3 name) |
| `[core] max_active_runs_per_dag` | `16` | Max concurrent DAG runs per DAG |

```ini
[core]
executor = LocalExecutor
parallelism = 32
max_active_tasks_per_dag = 16
max_active_runs_per_dag = 8
```

---

## How LocalExecutor Works Internally

```mermaid
flowchart TD
    A([Scheduler detects task ready to run]) --> B[Scheduler submits task to LocalExecutor]
    B --> C{Current running tasks < parallelism?}
    C -->|No| D[Task queued — wait for slot]
    D --> C
    C -->|Yes| E[Fork a new subprocess]
    E --> F[Subprocess executes task via airflow tasks run]
    F --> G{Exit code?}
    G -->|0| H[Task marked SUCCESS]
    G -->|non-zero| I[Task marked FAILED]
    H --> J[Subprocess exits, slot freed]
    I --> J

    style A fill:#4a90d9,color:#fff
    style H fill:#27ae60,color:#fff
    style I fill:#e74c3c,color:#fff
```

Each task subprocess:
1. Is a full Python process — it imports Airflow and the DAG file
2. Connects to the metadata database to update task state
3. Executes the operator's `execute()` method
4. Exits when the task is complete

---

## LocalExecutor vs SequentialExecutor

| Feature | SequentialExecutor | LocalExecutor |
|---|---|---|
| **Parallelism** | 1 task at a time | Many tasks simultaneously |
| **Database required** | SQLite (default) | PostgreSQL or MySQL (required) |
| **Setup complexity** | Zero | Minimal |
| **Best for** | Development, testing, tutorials | Small-medium production |
| **Subprocess isolation** | No (single process) | Yes (each task is a subprocess) |
| **Scheduler co-location** | Same process as scheduler | Separate subprocess per task |

**Important:** `LocalExecutor` requires a proper database (PostgreSQL or MySQL). SQLite does not support the concurrent writes that happen when multiple tasks complete simultaneously. Always use PostgreSQL with LocalExecutor.

---

## LocalExecutor vs CeleryExecutor

| Feature | LocalExecutor | CeleryExecutor |
|---|---|---|
| **Workers** | Scheduler machine only | Separate worker machines |
| **Scalability** | Limited to one machine | Horizontal scaling — add workers |
| **Message broker** | Not needed | Redis or RabbitMQ required |
| **Setup complexity** | Low | Medium-High |
| **Fault tolerance** | Single point of failure | Workers can fail independently |
| **Best for** | 1–50 tasks/hour, single machine | High throughput, multi-machine |
| **Cost** | Low | Higher (more components) |

---

## LocalExecutor vs KubernetesExecutor

| Feature | LocalExecutor | KubernetesExecutor |
|---|---|---|
| **Isolation** | Subprocess only | Full pod isolation |
| **Custom environments** | No (all tasks share Airflow's Python) | Yes (each task can use its own image) |
| **Infrastructure** | Just the Airflow machine | Kubernetes cluster required |
| **Scaling** | Bounded by machine resources | Bounded by cluster capacity |
| **Best for** | Simple workloads, single env | Multi-environment, cloud-native |

---

## When to Use LocalExecutor

**Good fit:**
- Small-to-medium teams with modest pipeline volumes
- Deployments on a single VM (e.g. a dedicated Airflow EC2 instance or bare metal)
- Pipelines with up to ~50-100 concurrent tasks
- Teams that want simplicity over scalability
- Early-stage data platforms graduating from development to production

**Not a good fit:**
- Workloads requiring more parallelism than one machine can provide
- Scenarios where Airflow worker nodes must be separate from the scheduler
- Pipelines where tasks have vastly different resource requirements
- Teams already operating Kubernetes or a managed Airflow service (like MWAA or Astro)

---

## Practical Configuration Example

A recommended production-ready `airflow.cfg` for LocalExecutor on a machine with 8 CPUs and 32 GB RAM:

```ini
[core]
executor = LocalExecutor

# Total concurrent tasks across all DAGs
# Rule of thumb: 2-4x the number of CPUs
parallelism = 24

# Max tasks per individual DAG running at once
max_active_tasks_per_dag = 12

# Max parallel DAG runs per DAG
max_active_runs_per_dag = 4

# Database — always PostgreSQL for LocalExecutor
sql_alchemy_conn = postgresql+psycopg2://airflow:airflow@postgres:5432/airflow

[scheduler]
# How often the scheduler loops (seconds) — lower = more responsive
scheduler_heartbeat_sec = 5

# Max tasks the scheduler will queue per scheduler loop
max_tis_per_query = 512
```

---

## Key Takeaways

- `LocalExecutor` enables parallelism without any extra infrastructure — just change one config line.
- It requires PostgreSQL or MySQL (not SQLite) due to concurrent database writes.
- All tasks run as subprocesses on the **same machine** as the scheduler — no separate workers.
- Use `parallelism` to control how many tasks run simultaneously; size it to your machine's CPUs.
- LocalExecutor is the right choice for small-to-medium production: simple, fast to set up, reliable.
- When you outgrow a single machine, migrate to CeleryExecutor or KubernetesExecutor.
