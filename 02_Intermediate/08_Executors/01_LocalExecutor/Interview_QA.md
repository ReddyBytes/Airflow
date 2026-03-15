# LocalExecutor — Interview Q&A

> Study guide for Apache Airflow 3. Story-first, beginner-friendly.

---

## Q1: What is LocalExecutor and how does it differ from SequentialExecutor?

**Answer:**

`LocalExecutor` runs task instances as **separate subprocesses** on the same machine as the Airflow scheduler, enabling true parallelism. Multiple tasks can execute simultaneously, up to the `parallelism` limit you configure.

`SequentialExecutor` (the default) runs tasks one at a time in a single thread. It is only suitable for development, testing, or tutorials.

The key practical difference: with SequentialExecutor, a 5-task DAG where all tasks are independent still runs those tasks one after another. With LocalExecutor, all 5 run at the same time (assuming enough CPU and `parallelism` headroom).

`SequentialExecutor` works with SQLite. `LocalExecutor` **requires PostgreSQL or MySQL** because concurrent subprocesses write to the metadata database simultaneously — SQLite cannot handle concurrent writes safely.

---

## Q2: How does parallelism work with LocalExecutor?

**Answer:**

Parallelism in LocalExecutor is controlled by three interlocking limits:

1. **`parallelism`** (global): the maximum number of tasks that can run simultaneously across **all** DAGs and all DAG runs. Think of this as the total thread-pool size.
2. **`max_active_tasks_per_dag`**: the maximum number of tasks that can run simultaneously within a **single DAG**. Even if the global `parallelism` has free slots, a DAG is throttled at this limit.
3. **`max_active_runs_per_dag`**: caps how many concurrent runs of the same DAG can exist (e.g. backfill scenarios).

When a task is ready, the scheduler checks all three limits. If any limit is saturated, the task waits in the queue until a slot opens.

Example: `parallelism=32`, `max_active_tasks_per_dag=8`. You have 3 DAGs running at once with 10 ready tasks each. Each DAG will run 8 tasks at the same time (DAG limit), and together they are using 24 of the 32 global slots — so 8 global slots remain available for other work.

---

## Q3: What database is required for LocalExecutor, and why?

**Answer:**

LocalExecutor requires **PostgreSQL** or **MySQL** (MariaDB). SQLite is not supported.

The reason: when LocalExecutor runs tasks in parallel, multiple subprocesses may update the metadata database simultaneously (marking tasks as running, succeeded, or failed). SQLite supports only one writer at a time and uses file-level locking. Under concurrent writes, SQLite will raise `database is locked` errors, causing data corruption or task state inconsistencies.

PostgreSQL is the recommended choice. It handles concurrent writes through proper MVCC (Multi-Version Concurrency Control) and row-level locking.

```ini
[database]
sql_alchemy_conn = postgresql+psycopg2://airflow:airflow@postgres:5432/airflow
```

---

## Q4: Does LocalExecutor require a message broker like Redis or RabbitMQ?

**Answer:**

No. This is one of LocalExecutor's biggest advantages.

CeleryExecutor requires a message broker (Redis or RabbitMQ) as the task queue between the scheduler and workers. KubernetesExecutor requires access to a Kubernetes API server.

LocalExecutor has no external dependencies beyond a PostgreSQL database (which you need for any production Airflow anyway). The scheduler itself acts as the task dispatcher — it simply forks a subprocess for each task.

This makes LocalExecutor the easiest executor to set up for production.

---

## Q5: How does LocalExecutor provide subprocess isolation?

**Answer:**

Each task runs in a dedicated Python subprocess created by forking the scheduler process. Key isolation properties:

- A **crash or exception** in one task's subprocess does not affect other running tasks or the scheduler.
- Each subprocess has its **own memory space** — tasks cannot accidentally share mutable Python state.
- The subprocess imports the DAG file independently, so it sees the task's operator code, hooks, and dependencies.
- When the task completes (success or failure), the subprocess exits and the operating system reclaims all its resources.

This is "process isolation" — not container isolation. All tasks share the same machine, filesystem, Python installation, and installed packages. If you need tasks to run in different Python environments or Docker containers, use KubernetesExecutor or KubernetesPodOperator instead.

---

## Q6: What happens if I set `parallelism` too high?

**Answer:**

Setting `parallelism` higher than your machine can support causes resource contention:

- **CPU contention**: if you have 4 CPUs but set `parallelism=50`, up to 50 processes compete for 4 CPU cores. Context switching overhead increases, and all tasks slow down.
- **RAM exhaustion**: each Airflow subprocess consumes memory (typically 100–300 MB each). 50 concurrent tasks × 200 MB = 10 GB just for tasks. If the machine runs out of RAM, the OS will start killing processes.
- **Database connection exhaustion**: each subprocess opens a database connection. PostgreSQL has a `max_connections` limit (default 100). Too many tasks overflow the connection pool.

**Rule of thumb:** Set `parallelism` to 2–3× your CPU count. For a machine with 8 CPUs, `parallelism=16` to `parallelism=24` is a safe starting point. Monitor CPU and RAM under load and adjust.

---

## Q7: When should you upgrade from LocalExecutor to CeleryExecutor?

**Answer:**

Upgrade to CeleryExecutor when you hit one or more of these situations:

1. **Single machine is not enough**: your task volume exceeds what one machine's CPU and RAM can handle, even with optimal `parallelism` settings.
2. **Scheduler single point of failure**: with LocalExecutor, if the scheduler machine goes down, all task execution stops. CeleryExecutor separates workers from the scheduler.
3. **Need horizontal scaling**: you want to add or remove worker machines dynamically (e.g., scale up before a heavy batch window, scale down overnight).
4. **Tasks have long queues**: you regularly see tasks waiting more than a few minutes for an open `parallelism` slot because the machine is fully loaded.
5. **Geographic distribution**: you need workers in different data centers or cloud regions (e.g., a task must run close to the data source).

If none of these apply, stay on LocalExecutor — it is simpler, cheaper, and equally reliable.

---

## Q8: Can the scheduler and webserver run on the same machine with LocalExecutor?

**Answer:**

Yes, and this is the typical LocalExecutor deployment pattern:

- One machine runs: PostgreSQL + Airflow scheduler + Airflow webserver.
- The scheduler forks subprocesses for each task on the same machine.
- There is no separate worker process or machine.

For a typical small-to-medium data platform, a VM with 8 CPUs and 32 GB RAM running all of this is perfectly sufficient and much simpler to maintain than a multi-machine Celery deployment.

---

## Q9: How do task logs work with LocalExecutor?

**Answer:**

Each task subprocess writes its logs to a file under `$AIRFLOW_HOME/logs/`. The log path follows the pattern:

```
$AIRFLOW_HOME/logs/{dag_id}/{run_id}/{task_id}/{try_number}.log
```

The Airflow webserver reads these log files when you click on a task instance in the UI. Since the scheduler and tasks all run on the same machine, the webserver can access the log files directly from the local filesystem.

If you want to preserve logs beyond the machine's lifecycle (e.g., for debugging after redeployment), configure a remote log backend (S3, GCS, Azure Blob) using `[logging] remote_logging = True`.

---

## Q10: What is the `max_active_tasks_per_dag` setting and why does it matter?

**Answer:**

`max_active_tasks_per_dag` (previously called `dag_concurrency` in Airflow 2.x) limits how many tasks from a **single DAG** can run simultaneously, regardless of the global `parallelism` setting.

This matters because without this limit, a high-parallelism DAG could monopolize all available task slots, starving other DAGs. For example, if `parallelism=32` and one DAG has 40 ready tasks, it would consume all 32 slots — leaving zero slots for other DAGs.

By setting `max_active_tasks_per_dag=8`, no single DAG can use more than 8 slots at once, ensuring fair access for all DAGs.

You can also override this per-DAG in the DAG definition:

```python
@dag(
    dag_id="my_parallel_dag",
    max_active_tasks=16,  # Override the global default for this DAG only
    ...
)
def my_parallel_dag():
    ...
```

---

## Q11: How does LocalExecutor compare to KubernetesExecutor for a team on Kubernetes?

**Answer:**

If your team already operates a Kubernetes cluster, KubernetesExecutor is almost always a better choice than LocalExecutor for the following reasons:

| Aspect | LocalExecutor | KubernetesExecutor |
|---|---|---|
| Task isolation | Subprocess only (shared machine) | Full pod (dedicated container) |
| Resource control | No per-task resource limits | CPU/memory requests and limits per pod |
| Custom environments | No (all tasks share Airflow's Python) | Yes (any Docker image per task) |
| Scaling | Bounded by one machine | Bounded by cluster capacity |
| Idle cost | Machine always running | Pods spin up and down; no idle workers |

The only reason to use LocalExecutor on Kubernetes would be very low task volumes where pod startup overhead (10–30 seconds) is unacceptable.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Next Executor** | [02_CeleryExecutor](../02_CeleryExecutor/) |
| **Section Root** | [08_Executors](../) |
