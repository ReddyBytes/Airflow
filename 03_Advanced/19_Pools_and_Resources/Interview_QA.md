# 11 · Pools & Resources — Interview Q&A

---

## Q1: What is an Airflow Pool and why would you use one?

**Answer:**

An Airflow Pool is a named resource bucket with a fixed number of concurrent execution slots. You assign tasks to a pool, and Airflow ensures that no more than the pool's slot limit of those tasks run at the same time.

You use pools when you need to protect a shared resource from being overwhelmed. Classic examples:
- A database that allows only 10 concurrent connections — you create a pool with 10 slots and assign all DB-querying tasks to it.
- An external API with a rate limit — you size the pool to stay within the limit.
- A worker with limited RAM that cannot handle more than 2 ML training jobs simultaneously.

Without pools, Airflow will happily schedule all eligible tasks in parallel up to its global `parallelism` limit, regardless of what that does to your downstream systems.

---

## Q2: How do you create a pool and assign tasks to it?

**Answer:**

Three ways to create a pool:

**Via CLI:**
```bash
airflow pools set db_pool 5 "Limits concurrent DB connections"
```

**Via UI:**
Admin > Pools > click + > fill in name, slots, description > Save.

**Via bulk import:**
```bash
airflow pools import pools.json
```

To assign a task to a pool, use the `pool` parameter on any operator:
```python
task = PythonOperator(
    task_id="query_db",
    python_callable=run_query,
    pool="db_pool",
    pool_slots=1,
)
```

The pool must exist in Airflow before the DAG runs, or the task will fail with a `PoolNotFound` error.

---

## Q3: What is `priority_weight` and when would you use it?

**Answer:**

`priority_weight` is an integer parameter (default: `1`) that controls the order in which tasks are dequeued when competing for pool slots. A higher value means higher priority — that task will be picked before lower-weighted tasks when a slot becomes available.

Example:
```python
critical_report = PythonOperator(
    task_id="critical_report",
    python_callable=run_report,
    pool="db_pool",
    priority_weight=10,   # This runs before everything else in the pool queue
)

nightly_archive = PythonOperator(
    task_id="nightly_archive",
    python_callable=archive_data,
    pool="db_pool",
    priority_weight=1,    # This waits at the back of the line
)
```

Use `priority_weight` when you have a mix of time-sensitive and background tasks competing for the same pool, and you need to guarantee that critical work completes first.

---

## Q4: What is the difference between `pool` and `max_active_tasks_per_dag`?

**Answer:**

| | `pool` | `max_active_tasks_per_dag` |
|--|--------|--------------------------|
| **Scope** | Shared across all DAGs | One specific DAG only |
| **Purpose** | Protect a shared resource | Limit concurrency within a DAG |
| **Configuration** | Task parameter | DAG-level parameter |

**`pool`** is resource-centric. You create one pool called `db_pool`, and 10 different DAGs can all reference it. None of them will exceed the combined slot limit together. It is about the resource.

**`max_active_tasks_per_dag`** is DAG-centric. It says "no matter what, this single DAG will not run more than N tasks at once." It does not affect other DAGs.

Use `pool` when multiple DAGs share the same resource. Use `max_active_tasks_per_dag` when you just want to throttle a single DAG.

---

## Q5: What happens when a task is assigned to a pool that does not exist?

**Answer:**

The task will fail immediately — it will not enter the `queued` state. Airflow will raise a `PoolNotFound` exception and mark the task as `failed`.

This is a common deployment gotcha: you deploy a DAG that references a new pool, but the pool has not been created in the environment yet. Always create pools before or at the same time as deploying DAGs that reference them.

The fix is to either:
1. Create the pool before deploying the DAG.
2. Use the `pools import` CLI command as part of your deployment pipeline.

---

## Q6: What is `pool_slots` and when would you set it to more than 1?

**Answer:**

`pool_slots` (default: `1`) tells Airflow how many pool slots a single task instance should consume. Normally one task = one slot. But if a task is exceptionally resource-heavy, you can make it consume multiple slots to prevent other tasks from running concurrently with it.

Example: you have an `ml_pool` with 4 slots. Most ML tasks consume 1 slot, but your large-model training job needs all the RAM — you do not want any other ML task running alongside it.

```python
train_large_model = PythonOperator(
    task_id="train_large_model",
    python_callable=train_gpt_model,
    pool="ml_pool",
    pool_slots=4,    # Consumes all 4 slots — nothing else in ml_pool can run
)
```

When this task runs, it occupies all 4 slots. No other task assigned to `ml_pool` can start until this task completes.

---

## Q7: How do Airflow Pools interact with different executors?

**Answer:**

Pools are an Airflow-level concept managed by the Scheduler, so they work with all executors:

- **SequentialExecutor**: Tasks still respect pool limits, but since only one task runs at a time anyway, pools rarely matter here.
- **LocalExecutor**: Pool limits are enforced by the Scheduler before tasks are handed to the local process pool.
- **CeleryExecutor**: Pools are enforced before tasks are sent to Celery queues. A task waiting for a pool slot never reaches the Celery broker. The `queue` parameter (separate from `pool`) determines which Celery worker handles the task once a slot is free.
- **KubernetesExecutor**: Pool limits are enforced before a pod is spawned. If all pool slots are occupied, no pod is created for the waiting task.

Key point: pool enforcement happens in the Scheduler, before the executor is involved. The executor only sees tasks that have already acquired a pool slot.

---

## Q8: How would you use pools to handle an API that allows only 5 requests per minute?

**Answer:**

Pools alone control concurrency (parallel tasks), not rate over time. However, combining pools with appropriate task design handles most rate-limiting scenarios.

**Step 1 — Create the pool:**
```bash
airflow pools set api_pool 5 "Rate limits external API to 5 concurrent requests"
```

**Step 2 — Assign all API tasks to the pool:**
```python
for item in items_to_fetch:
    PythonOperator(
        task_id=f"fetch_{item}",
        python_callable=fetch_from_api,
        op_kwargs={"item": item},
        pool="api_pool",
    )
```

This limits concurrent requests to 5. If the API's limit is "5 requests per second" rather than "5 concurrent connections," you would also add a `time.sleep(1)` inside your callable, or use a more sophisticated rate-limiting library inside the function itself.

For strict time-based rate limits, pools handle the concurrency ceiling while your task code handles the timing.
