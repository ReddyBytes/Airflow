# Executors — Interview Q&A

## Beginner Level

**Q1: What is an executor in Apache Airflow?**
**A:** The executor is the component that determines how and where tasks are actually run. The Scheduler decides *what* to run and *when*; the Executor handles the *how*. It sits inside the Scheduler process and dispatches tasks to workers (subprocesses, containers, or pods).

**Q2: What are the main executors available in Airflow?**
**A:** The main executors are:
- **SequentialExecutor** — one task at a time, no parallelism (dev only)
- **LocalExecutor** — multiple tasks in parallel using Python subprocesses on one machine
- **CeleryExecutor** — distributed workers via Celery message queue
- **KubernetesExecutor** — each task runs in its own Kubernetes pod
- **EdgeExecutor** (Airflow 3) — tasks on remote/edge devices

**Q3: How do you configure which executor to use?**
**A:** Set it in `airflow.cfg` under `[core]`:
```ini
executor = LocalExecutor
```
Or via environment variable:
```bash
AIRFLOW__CORE__EXECUTOR=CeleryExecutor
```
Restart Airflow after changing this.

**Q4: Which executor should you use for development?**
**A:** `SequentialExecutor` — it's the default and requires no additional infrastructure. Tasks run one at a time, which is fine for testing DAG logic. Never use it in production.

**Q5: Does changing the executor require you to change your DAGs?**
**A:** No. The executor is completely transparent to your DAGs. A DAG written for LocalExecutor runs identically on CeleryExecutor or KubernetesExecutor without any code changes.

---

## Intermediate Level

**Q6: What is the difference between LocalExecutor and CeleryExecutor?**
**A:**
| | LocalExecutor | CeleryExecutor |
|---|---|---|
| **Workers** | Subprocesses on scheduler machine | Separate worker processes (can be on different machines) |
| **Broker** | Not needed | Requires Redis or RabbitMQ |
| **Scale** | Single machine only | Multiple machines |
| **Setup** | Simple | More complex |
| **Best for** | Small-medium prod | Large-scale prod |

**Q7: What infrastructure does CeleryExecutor require?**
**A:** CeleryExecutor needs:
1. A **message broker** (Redis or RabbitMQ) — the Scheduler pushes task messages here
2. A **result backend** (Postgres, Redis) — workers write task results here
3. One or more **Celery worker processes** — separate from the Scheduler

**Q8: How does KubernetesExecutor handle task isolation?**
**A:** KubernetesExecutor creates a fresh Kubernetes pod for every task instance. The pod runs, completes the task, and terminates. This gives:
- **Complete isolation** — a crash in one task cannot affect others
- **Dynamic resources** — each task can request different CPU/memory
- **Clean state** — no shared filesystem or process state between tasks
The tradeoff is pod startup overhead (~10–30 seconds per task).

**Q9: What is `parallelism` in Airflow configuration?**
**A:** `parallelism` (default: 32) is the maximum number of task instances that can run simultaneously across ALL DAGs in the entire Airflow instance. If you have 100 tasks ready to run, only 32 will actually execute at once. Related settings: `max_active_tasks_per_dag` (per-DAG limit) and `max_active_runs_per_dag` (concurrent DAG run limit).

**Q10: What is the CeleryKubernetesExecutor?**
**A:** A hybrid executor that routes tasks to either Celery workers or Kubernetes pods based on a queue. You can tag tasks with `queue="kubernetes"` to run them in pods (for heavy workloads), while everything else runs on Celery workers (faster startup). Useful for organizations that have both fast, lightweight tasks and resource-intensive ML/data tasks.

---

## Advanced Level

**Q11: What happens to a running task when an Airflow worker crashes?**
**A:** Behavior depends on the executor:
- **LocalExecutor**: the task's subprocess is killed; Airflow marks it as failed after heartbeat timeout
- **CeleryExecutor**: the Celery worker crashes; the task may be in an "orphaned" state until Airflow's zombie detection picks it up and marks it failed (can take a few minutes)
- **KubernetesExecutor**: the pod is gone; Airflow detects the pod termination and marks the task failed — cleaner recovery

**Q12: How does Airflow detect zombie tasks?**
**A:** The Scheduler runs a "zombie detection" loop that checks for task instances that are marked as "running" in the metadata DB but haven't sent a heartbeat in `scheduler_zombie_task_threshold` seconds (default: 300s). These are marked as failed and can be retried if configured.

**Q13: Can you run multiple executors at the same time?**
**A:** Yes, via `CeleryKubernetesExecutor`. In Airflow 3, the architecture is moving toward pluggable executors with multi-executor support, where you can configure different task groups to use different executors.

**Q14: How do you assign tasks to specific Celery queues?**
**A:** Use the `queue` parameter on any operator:
```python
heavy_task = PythonOperator(
    task_id="heavy_processing",
    python_callable=process_data,
    queue="high_memory_workers"   # Routes to workers listening on this queue
)
```
Workers subscribe to specific queues: `airflow celery worker -q high_memory_workers`

---

## 📂 Navigation

| File | |
|---|---|
| 📖 [Theory.md](./Theory.md) | Executor overview |
| ⚡ [Cheatsheet.md](./Cheatsheet.md) | Quick reference |
| 🎯 **Interview_QA.md** | ← you are here |

⬅️ **Prev:** [Sensors](../07_Sensors/Interview_QA.md) &nbsp;&nbsp;&nbsp; ➡️ **Next:** [LocalExecutor](./01_LocalExecutor/Theory.md)
