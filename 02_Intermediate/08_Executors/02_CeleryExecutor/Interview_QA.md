# CeleryExecutor — Interview Q&A

> Study guide for Apache Airflow 3. Story-first, beginner-friendly.

---

## Q1: What is Celery and why does Airflow use it?

**Answer:**

Celery is an open-source distributed task queue library for Python. It allows you to define units of work (tasks) and run them asynchronously across one or more worker processes — often on separate machines.

Airflow uses Celery as the underlying distributed execution engine for `CeleryExecutor`. When the Airflow scheduler decides a task is ready to run, it does not run the task itself; it pushes a message to a Celery broker. A Celery worker somewhere in the fleet receives that message and executes the Airflow task. The result is stored in a result backend, and the scheduler reads it to update the task's state in the metadata database.

Airflow benefits from Celery's mature infrastructure for distributed job queuing, worker monitoring (via Flower), and queue-based task routing — without having to build that infrastructure from scratch.

---

## Q2: What is the role of the broker in CeleryExecutor?

**Answer:**

The broker is a **message queue** that sits between the Airflow scheduler and the Celery workers. It decouples the two components so they do not need to communicate directly.

The scheduler writes a task message to the broker: "execute DAG `my_dag`, task `my_task`, run ID `my_run_2025-01-01`." The broker holds this message until a worker is available. A worker then reads the message from the queue and runs the task.

Without the broker:
- The scheduler would need to know which workers are available and directly send tasks to them.
- If a worker crashes, the in-flight task would be lost.
- Scaling workers would require re-configuring the scheduler.

With the broker:
- The scheduler just pushes to a queue — it does not care how many workers exist.
- Workers just pull from the queue — they do not care about the scheduler.
- Tasks are held in the queue if no workers are available; they are not lost.

Supported brokers: **Redis** (most common) and **RabbitMQ**.

---

## Q3: What is the result backend and what is it used for?

**Answer:**

The result backend stores the outcome of each Celery task — specifically, whether the task succeeded or failed and any return value.

After a worker finishes a task, it writes the result to the result backend. The Airflow scheduler reads the result to update the task instance state (SUCCESS, FAILED) in the PostgreSQL metadata database.

Common result backend options:

1. **PostgreSQL** (`db+postgresql://...`) — recommended. Reuses the existing metadata DB. No extra infrastructure. Slightly slower than Redis but reliable and durable.
2. **Redis** (`redis://...`) — fast but volatile if Redis is not configured with persistence. Good for high-throughput deployments.

```ini
# airflow.cfg
[celery]
# Using the existing PostgreSQL metadata DB as result backend
result_backend = db+postgresql://airflow:airflow@postgres/airflow
```

---

## Q4: How are tasks dispatched from the scheduler to workers?

**Answer:**

The dispatch flow is:

1. The **scheduler** scans the metadata database for task instances in the `scheduled` state.
2. For each ready task, the scheduler creates a Celery task message containing the execution context (dag_id, task_id, run_id, execution_date, etc.).
3. The scheduler publishes the message to the **broker** (Redis or RabbitMQ queue).
4. A **Celery worker** that is subscribed to that queue receives the message.
5. The worker runs `airflow tasks run <dag_id> <task_id> <execution_date>` in a subprocess.
6. The worker marks the result (success or failure) in the **result backend**.
7. The **scheduler** reads the result from the result backend and updates the task instance state in the metadata DB.
8. Downstream tasks that were waiting on this task are now marked as `scheduled` and the cycle repeats.

---

## Q5: What is `worker_concurrency` and how do you set it?

**Answer:**

`worker_concurrency` (config key: `[celery] worker_concurrency`) controls how many tasks a **single Celery worker process** can handle simultaneously. Each "slot" within a worker is a subprocess.

Default: `16`.

Setting guidance:
- Set it close to the number of **CPU cores** on the worker machine.
- If tasks are I/O bound (HTTP calls, database queries), you can set it higher (2–4× CPUs) because CPUs are not fully utilized.
- If tasks are CPU bound (data processing, ML), keep it at or below the CPU count.
- Leave some headroom for the Celery worker process itself and the OS.

```ini
[celery]
worker_concurrency = 8   # For a 4-CPU worker machine with CPU-bound tasks
worker_concurrency = 16  # For a 4-CPU worker machine with I/O-bound tasks
```

```bash
# Can also be set via CLI flag at worker startup
airflow celery worker --concurrency 12
```

---

## Q6: How does queue routing work in CeleryExecutor?

**Answer:**

Queues let you route specific tasks to specific worker pools. Each worker listens on one or more queues. Tasks specify which queue they belong to.

Use cases:
- Route GPU-heavy ML tasks to workers on GPU machines
- Route long-running "heavy" tasks to dedicated workers so they do not block light tasks
- Route tasks that need specific software (e.g. Spark) to workers with Spark installed

**DAG side:**

```python
@task(queue="gpu_workers")
def train_model():
    pass
```

**Worker side:**

```bash
# GPU worker — only handles tasks sent to gpu_workers queue
airflow celery worker --queues gpu_workers

# General worker — handles default queue
airflow celery worker --queues default

# Multi-queue worker
airflow celery worker --queues default,reporting
```

If a task is sent to a queue that no worker is listening on, it sits in the queue indefinitely — a common debugging gotcha.

---

## Q7: What is the difference between CeleryExecutor and CeleryKubernetesExecutor?

**Answer:**

`CeleryKubernetesExecutor` is a hybrid executor (available in Airflow 2.x and 3.x) that uses both CeleryExecutor and KubernetesExecutor simultaneously. You can route some tasks to Celery workers and others to Kubernetes pods within the same DAG.

- Default queue → tasks go to Celery workers
- Queue named `kubernetes` → tasks go to Kubernetes pods

```python
@task(queue="kubernetes")
def isolated_task():
    # This task gets its own Kubernetes pod
    pass

@task  # No queue = default queue = Celery worker
def regular_task():
    pass
```

Use `CeleryKubernetesExecutor` when:
- Most tasks are fine on Celery workers (fast, low overhead)
- A small subset of tasks need full container isolation or custom Docker images (use K8s)
- You want the benefits of both without full KubernetesExecutor overhead

---

## Q8: What happens if a Celery worker crashes mid-task?

**Answer:**

When a worker crashes:

1. The task's Celery message is **not acknowledged** — it remains in the broker queue (if `visibility_timeout` has not expired).
2. After the `visibility_timeout` passes, the broker makes the message visible again.
3. Another available worker picks up the message and re-executes the task.
4. In Airflow, this appears as the task being retried.

Key configuration to tune:

```ini
[celery_broker_transport_options]
# Must be longer than your longest task's expected runtime
# Default: 21600 seconds (6 hours)
visibility_timeout = 21600
```

If `visibility_timeout` is too short and a long task is running on a worker that doesn't crash, the broker may deliver the message to a second worker — causing the task to run twice. Always set it longer than your longest expected task.

---

## Q9: What is the Flower dashboard and what can you monitor with it?

**Answer:**

Flower is a web-based monitoring tool for Celery. It is started with `airflow celery flower` and available at port `5555` by default.

Key things to monitor:

- **Workers tab**: active workers, their status (online/offline), tasks processed, failed tasks, and current task count per worker
- **Tasks tab**: history of recent tasks including execution time and state
- **Broker tab**: queue depth (backlog size) — a growing backlog means workers are falling behind and you need to scale up
- **Monitor tab**: real-time charts of task rates

Flower is lightweight and sufficient for most CeleryExecutor deployments. For more advanced monitoring, integrate with Prometheus + Grafana using the `flower_unauthenticated_api` configuration to expose metrics.

---

## Q10: How do you ensure DAG files are available on all Celery workers?

**Answer:**

This is one of the key operational challenges with CeleryExecutor: every worker needs access to the same DAG files as the scheduler.

Common approaches:

1. **Shared filesystem** (NFS, EFS, Azure Files): mount the same `dags/` directory on all machines. Workers see DAG updates immediately. Simple but adds a network dependency.

2. **Git sync**: each worker runs a process that pulls DAG files from a Git repository on a schedule. Workers eventually see updates with a delay (configurable, usually 1–5 minutes).

3. **Docker image with DAGs baked in**: build a new Docker image every time DAGs change. Workers are restarted with the new image. Works well in Kubernetes-based Celery setups.

4. **S3/GCS sync**: a sidecar process on each worker syncs DAG files from object storage.

The shared filesystem approach is most common in Docker-based deployments (shared volume). Git sync is most common in Kubernetes-based deployments.

---

## Q11: When should you NOT use CeleryExecutor?

**Answer:**

Despite its power, CeleryExecutor is not always the right choice:

- **Small workloads on a single machine**: LocalExecutor is simpler and has no broker overhead. If you have ≤ 50 tasks/hour on a single VM, stay on LocalExecutor.
- **You are already on Kubernetes**: KubernetesExecutor gives you better isolation, per-task resource control, and no idle worker cost. Celery workers on K8s add complexity without using K8s's strengths.
- **Very short tasks** (< 5 seconds each): broker round-trip and worker overhead become significant. LocalExecutor is faster for quick tasks.
- **Operational simplicity is critical**: CeleryExecutor adds a broker, workers, and optionally Flower to your infrastructure. More components = more things to monitor, upgrade, and debug.

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Code Examples** | [Code_Example.md](./Code_Example.md) |
| **Prev Executor** | [01_LocalExecutor](../01_LocalExecutor/) |
| **Next Executor** | [03_KubernetesExecutor](../03_KubernetesExecutor/) |
| **Section Root** | [08_Executors](../) |
