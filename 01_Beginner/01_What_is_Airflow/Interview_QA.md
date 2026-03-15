# 01 · Core Concepts — Interview Q&A

15 questions covering beginner through advanced. Try to answer each question out loud before reading the answer.

---

## Beginner (Questions 1–5)

---

### Q1. What is Apache Airflow and what problem does it solve?

**Answer:**

Apache Airflow is an open-source platform for authoring, scheduling, and monitoring workflows. A workflow is a set of tasks that need to run in a specific order.

The core problem it solves is the limitation of cron jobs. With cron, you can schedule tasks by time, but you cannot express dependencies (task B should only run if task A succeeded), you get no visibility (you cannot see which jobs ran or failed), and there are no automatic retries. Airflow solves all of these: you define explicit task dependencies, every run is tracked in a database and shown in a UI, and failed tasks can be retried automatically.

---

### Q2. What is a DAG?

**Answer:**

DAG stands for Directed Acyclic Graph. In graph theory, a directed graph means edges have direction (A → B, not B → A), and acyclic means there are no cycles (if A depends on B, B cannot also depend on A).

In Airflow, a DAG is a Python file that defines a workflow. It contains:
- Tasks (units of work)
- Dependencies between tasks (which must run before which)
- Schedule configuration (when to run)
- A start date

The DAG itself does not run the logic — it is just the definition. Airflow's Scheduler reads DAG files and creates actual runs from them.

---

### Q3. What are the main components of Airflow?

**Answer:**

Six main components:

1. **Scheduler** — reads DAG files, determines when runs are due, submits tasks to the Executor, and monitors task states. The brain of Airflow.
2. **Webserver** — a Flask web application that provides the dashboard UI on port 8080. Reads from the Metadata Database.
3. **Metadata Database** — a relational database (PostgreSQL in production) that stores all state: DAG definitions, task runs, connections, variables, user accounts. The single source of truth.
4. **Executor** — defines how tasks are run. Is it the same process? Separate machines? Containers? Different executors suit different scale requirements.
5. **Worker** — the process or pod that actually executes a task's code.
6. **Triggerer** — handles deferrable tasks (tasks that wait for an external event). Instead of occupying a full worker slot while polling, deferrable tasks yield back to the Triggerer.

---

### Q4. What is the difference between a DAG and a Task?

**Answer:**

A DAG is the whole workflow — it is the container that holds tasks and defines their relationships and schedule.

A Task is one unit of work within a DAG. For example, a DAG might be called `daily_sales_etl`. Inside it, you might have three tasks: `extract_from_api`, `transform_data`, and `load_to_warehouse`.

A task is created from an Operator. An Operator is a reusable template (a Python class) for a type of work. `BashOperator` runs a bash command. `PythonOperator` runs a Python function. `EmailOperator` sends an email.

Think of it this way: **DAG = recipe card. Task = one step in the recipe. Operator = the category of step (chop, stir, bake).**

---

### Q5. How is Airflow different from a cron job?

**Answer:**

| Feature | Cron | Airflow |
|---------|------|---------|
| Task dependencies | Not supported | Explicit with `>>` operator |
| Visibility / UI | None | Full dashboard |
| Automatic retries | No | Yes, configurable per task |
| Backfilling | No | Yes, built-in |
| Failure alerts | No | Yes |
| Version control | Not practical | Yes, Python files in Git |
| Scalability | Single machine | Multiple workers/executors |

Cron is great for simple, independent tasks on a single machine. Airflow is built for complex, dependent, multi-step pipelines that need visibility and reliability.

---

## Intermediate (Questions 6–10)

---

### Q6. How does the Scheduler work internally?

**Answer:**

The Scheduler is a continuous loop. On each iteration it does the following:

1. **DAG discovery** — scans the `dags/` folder for Python files and parses them (default: every 30 seconds per file). Valid DAGs are stored in the Metadata Database.
2. **Trigger determination** — for each active DAG, checks: "Is the next scheduled run time in the past?" If yes, a new DAG Run is created with state `running`.
3. **Task eligibility** — for each running DAG Run, looks at each task. If all upstream dependencies are satisfied (all upstream tasks have state `success`), the task is marked `scheduled`.
4. **Task submission** — passes scheduled tasks to the Executor, which marks them `queued`.
5. **Health check** — monitors running tasks, updates states in the database.

The Scheduler does not run task code — it only orchestrates. In Airflow 2.x, the Scheduler was redesigned to run as multiple concurrent processes for high availability.

---

### Q7. What is the role of the Metadata Database?

**Answer:**

The Metadata Database is the backbone of Airflow. It stores:

- All DAG definitions and configurations parsed from files
- Every DAG Run and its state (running, success, failed)
- Every Task Instance and its state, start time, end time, log location
- Connections (credentials for external systems)
- Variables (key-value config)
- User accounts and RBAC permissions
- XCom values (data passed between tasks)
- Pool definitions

Both the Scheduler and Webserver are stateless — they derive everything they show or act on from the Metadata Database. If you delete the database, you lose all history.

PostgreSQL is strongly recommended for production. SQLite (the default) is single-connection and cannot support parallel task execution.

---

### Q8. What are the main types of Executors?

**Answer:**

| Executor | How it works | Use case |
|----------|-------------|----------|
| `SequentialExecutor` | Runs one task at a time in the same process as the Scheduler | Local development only |
| `LocalExecutor` | Runs tasks as subprocesses on the same machine as the Scheduler | Small-scale production on one machine |
| `CeleryExecutor` | Distributes tasks to a pool of Celery workers via a message queue (Redis or RabbitMQ) | Mid-to-large scale, traditional infrastructure |
| `KubernetesExecutor` | Launches each task in its own Kubernetes pod | Large scale, cloud-native, dynamic resource allocation |
| `CeleryKubernetesExecutor` | Hybrid: some tasks on Celery, some on K8s | Mixed workloads |

The Executor is set in `airflow.cfg` with the `executor` key. Changing the Executor does not require changing your DAG code.

---

### Q9. What happens when Airflow starts up for the first time?

**Answer:**

1. Airflow reads `airflow.cfg` (or environment variables) to find the Metadata Database connection.
2. It runs database migrations — creates all the required tables using SQLAlchemy.
3. The Webserver starts a Flask app on port 8080.
4. The Scheduler starts its loop — begins scanning the `dags/` folder.
5. If no admin user exists, you create one with `airflow users create`.
6. Once the Scheduler has parsed DAG files, DAGs appear in the Webserver UI.

On startup, Airflow does NOT automatically create runs for your DAGs. Runs are created when the Scheduler determines the `schedule_interval` has elapsed since the last run (or since `start_date` if there has never been a run).

---

### Q10. What is the Triggerer and when do you need it?

**Answer:**

The Triggerer is a process introduced in Airflow 2.2 that enables **deferrable operators**.

A deferrable operator is one that spends most of its time waiting for something external to happen — a file to appear, an HTTP endpoint to return 200, a Spark job to finish. Traditionally, this would occupy a full worker slot for the entire wait duration.

With the Triggerer:
1. The task starts on a worker.
2. It detects it needs to wait, and "defers" itself — suspending execution and yielding back to the Triggerer.
3. The worker slot is freed immediately.
4. The Triggerer polls asynchronously (using Python `asyncio`) for the condition to be met.
5. When ready, it re-queues the task to a worker to finish.

This dramatically reduces the number of workers needed for I/O-heavy pipelines. You need the Triggerer running if you use any `*Async` variants of sensors or operators.

---

## Advanced (Questions 11–15)

---

### Q11. How would you design a production Airflow setup?

**Answer:**

A production setup should be highly available, scalable, and observable. A typical design:

**Infrastructure:**
- **Kubernetes** or Docker Swarm for container orchestration
- **PostgreSQL** (RDS or Cloud SQL) for the Metadata Database — not SQLite
- **Redis** or RabbitMQ as the Celery message broker (if using CeleryExecutor)
- **Object storage** (S3, GCS) for remote log storage
- **Secrets manager** (AWS Secrets Manager, HashiCorp Vault) for credentials

**Airflow components:**
- Multiple Scheduler replicas (Airflow 2.x supports HA Scheduler)
- Multiple Webserver replicas behind a load balancer
- Auto-scaling Celery worker pool (or KubernetesExecutor for per-task pods)
- Triggerer for deferrable tasks

**Operational practices:**
- DAGs deployed via CI/CD pipeline (not manual file copy)
- Alerting on task failure (PagerDuty, Slack, email)
- SLA monitoring
- Regular metadata DB cleanup (using `airflow db clean`)
- Role-Based Access Control (RBAC) configured

---

### Q12. How do you handle DAG failures in production?

**Answer:**

A layered approach:

1. **Automatic retries** — set `retries` and `retry_delay` in `default_args` for all tasks. Most transient failures (network timeouts, rate limits) resolve on retry.

2. **Alerting** — set `on_failure_callback` to send a Slack message, PagerDuty alert, or email. Can be set at the task or DAG level.

3. **SLA misses** — set `sla` on tasks to alert if a task has not finished within N minutes. Useful for catching tasks that are running but stuck.

4. **Dead-letter queues** — for CeleryExecutor, configure what happens to tasks that never get acknowledged.

5. **Manual intervention** — via the UI: you can clear a failed task instance (resets it to `none` so it re-runs) or mark it as success if you resolved the issue manually.

6. **Incident runbooks** — document common failure modes and their remediation steps. Link to them in DAG code comments.

7. **Backfill after recovery** — if a run was missed while fixing an outage, use `airflow dags backfill` to re-run the affected date range.

---

### Q13. How does Airflow scale to handle thousands of DAGs?

**Answer:**

Scaling Airflow involves multiple dimensions:

**Horizontal Scheduler scaling:**
Airflow 2.x supports multiple Scheduler instances via a leader-election mechanism in the Metadata Database. Each Scheduler processes a subset of DAGs, reducing parse time and task submission latency.

**Executor scaling:**
- CeleryExecutor: add more worker nodes. Workers are stateless and can be scaled up/down dynamically.
- KubernetesExecutor: each task gets its own pod. Scaling is handled by Kubernetes natively.

**Database scaling:**
- Use a managed PostgreSQL service (RDS, Cloud SQL) with read replicas.
- Run `airflow db clean` regularly to remove old task instance records.
- Tune `sql_alchemy_pool_size` to handle concurrent DB connections.

**DAG parsing optimization:**
- Keep DAG files lightweight — no I/O or DB calls at parse time.
- Use `dag_dir_list_interval` and `min_file_process_interval` to balance freshness vs. CPU overhead.
- Organize DAGs into sub-folders and use `.airflowignore` to exclude non-DAG files.

**Worker sizing:**
- Set `worker_concurrency` to control how many tasks a single Celery worker runs simultaneously.
- Size worker machines appropriately for task memory/CPU requirements.
- Use Pools to limit concurrency for resource-constrained tasks (e.g., max 5 DB-heavy tasks at once).

---

### Q14. What is idempotency and why does it matter in Airflow?

**Answer:**

An idempotent task is one where running it multiple times produces the same result as running it once. This matters in Airflow for two reasons:

1. **Retries** — if a task fails halfway through and retries, it will re-run from the beginning. If the task is not idempotent, it might double-insert rows, double-send emails, or corrupt data.

2. **Backfilling** — backfill re-runs historical DAG runs. If a task is not idempotent, backfilling creates duplicates.

**How to make tasks idempotent:**
- Use `INSERT INTO ... ON CONFLICT DO NOTHING` (upsert) instead of plain `INSERT`
- Delete output before writing: `TRUNCATE TABLE x; INSERT INTO x ...`
- For file writes: write to a temp path, then atomically rename to the final path
- For API calls: use idempotency keys if the API supports them
- Check before acting: "does this record already exist? If so, skip."

---

### Q15. What is the difference between execution_date and logical_date in Airflow 2.x?

**Answer:**

In Airflow, runs are defined by a **logical date** (called `execution_date` in older versions, renamed `logical_date` in Airflow 2.2+).

The logical date is the *start of the interval* that the DAG run covers, NOT the actual clock time when the run executes.

**Example:**
A DAG with `schedule_interval="@daily"` and `start_date=2024-01-01` will have:
- Its first run **triggered** at `2024-01-02 00:00` (after the first interval completes)
- With `logical_date = 2024-01-01` (the start of the day it covered)

This is a common source of confusion. The run is always "one interval behind" in terms of wall clock time, but it covers the period starting at the logical date.

**Why it works this way:** Airflow was designed for batch pipelines that process data for a completed time window. The logical date identifies *what data* the run is about, not *when* the run happened.

In Airflow 2.2+, `execution_date` is soft-deprecated. Use `logical_date` in new code. In templates, use `{{ ds }}` for the logical date formatted as `YYYY-MM-DD`.

---

## 📂 Navigation

⬅️ **Prev:** [Cheatsheet](./Cheatsheet.md) | 🏠 **[Home](../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:** [02 · Installation & Setup — Theory](../02_Installation_and_Setup/Theory.md)
