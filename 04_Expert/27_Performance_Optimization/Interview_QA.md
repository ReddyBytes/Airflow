# 27 — Performance Optimization: Interview Q&A

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

**Q1: What causes scheduler lag and how do you diagnose it?**

Scheduler lag — tasks that should start at T but don't start until T+5min — has several root causes: (1) DAG files are slow to parse, blocking the scheduling loop (look for long `dag.loading-duration` metrics), (2) too many DAG runs queued simultaneously due to catchup, (3) the metadata DB is slow due to table bloat or missing indexes, (4) the scheduler is CPU-bound because `parsing_processes` is too low. Diagnose with StatsD metrics: `scheduler.scheduler_loop_duration` should be under 1-2 seconds. If it's consistently over 10 seconds, the scheduler is overloaded. Start with increasing `min_file_process_interval` from 30 to 300 — this alone often halves scheduler load.

---

**Q2: What is `min_file_process_interval` and what value should you use in production?**

`min_file_process_interval` is how often (in seconds) Airflow re-parses each DAG file to detect changes. The default is 30 seconds, meaning every DAG file is parsed at least every 30 seconds. This is appropriate for development where you want rapid feedback, but catastrophic in production with 500+ DAG files — it means constant parsing, constant DB writes (updating the `dag` table), and a constantly busy file processor. In production with stable DAGs, set it to 300–600 seconds. DAG changes will take up to 5–10 minutes to appear — this is acceptable in production where DAGs are deployed via CI/CD, not hand-edited.

---

**Q3: Why should you never call `Variable.get()` at the DAG module level?**

Airflow's file processor imports every DAG file at `min_file_process_interval`. Any code at module level runs on every import. `Variable.get()` makes a database call, meaning every DAG import triggers a DB query. With 100 DAG files and a 30-second parse interval, that's 100 DB queries every 30 seconds just for variable access — plus it introduces a startup dependency (no DB, no DAG parsing). The fix is simple: move all `Variable.get()` calls inside task callables or hooks, where they only run when the task actually executes.

---

**Q4: How do sensors impact performance and what is the correct approach?**

Sensors in the default `poke` mode hold a worker slot for their entire duration — a sensor waiting 2 hours occupies one worker slot for 2 hours. With 50 such sensors, you've consumed 50 worker slots that could be running actual tasks. Use `mode="reschedule"`: the sensor sets itself to `up_for_reschedule` state between pokes and releases the worker slot. The scheduler re-queues it after `poke_interval`. For Kubernetes deployments or when you have hundreds of sensors, use `deferrable=True` — the task suspends entirely and uses zero worker slots, with the Triggerer process handling the async polling.

---

**Q5: What is a pool and when should you use it?**

A pool is a concurrency limit applied to a named group of tasks, independent of the global `parallelism` limit. Create a pool named `warehouse_heavy` with 5 slots, then assign slow warehouse queries to that pool — only 5 can run simultaneously regardless of how many workers are available. Use pools when: (1) a downstream system can't handle more than N concurrent connections (database, API rate limits), (2) certain tasks are resource-intensive and you don't want them starving other tasks, (3) you need to implement fair sharing between business units or use cases. `pool_slots=N` lets a single task consume multiple slots (for "heavy" tasks).

---

**Q6: How do you use the DAG factory pattern to improve performance?**

Instead of 50 separate `.py` files with nearly identical DAG definitions, write one file that generates all 50 DAGs programmatically:
```python
# One file, parsed once, produces 50 DAGs
for table in TABLES:
    with DAG(dag_id=f"etl_{table}", ...) as dag:
        ...
    globals()[f"etl_{table}"] = dag
```
Benefits: (1) the file processor parses 1 file instead of 50, reducing parse time by 98%, (2) bugs fixed in the template fix all DAGs simultaneously, (3) adding a new table requires one config change, not a new file. The key constraint: `TABLES` must be defined from a static config (list, YAML file) not a DB query — otherwise you reintroduce the top-level DB call problem.

---

**Q7: How do you optimize the metadata database for large Airflow deployments?**

Five techniques: (1) Use PostgreSQL — it handles Airflow's concurrent read/write pattern far better than MySQL. (2) Schedule `airflow db clean` weekly to delete old task instance and DAG run records — a table with 10M+ rows is the most common hidden performance killer. (3) Tune `autovacuum` on the `task_instance` table, which has very high write rates. (4) Tune the SQLAlchemy connection pool: `sql_alchemy_pool_size = 5`, `sql_alchemy_max_overflow = 10`, `sql_alchemy_pool_recycle = 1800`. (5) Put the metadata DB on fast SSD storage — it's the single most latency-sensitive component.

---

**Q8: What is `max_active_runs_per_dag` and why does it matter for catchup?**

`max_active_runs_per_dag` limits how many concurrent runs of the same DAG can be active simultaneously. The default is 16. The danger: when a daily DAG is created or unpaused with `catchup=True` and 6 months of history, Airflow immediately tries to schedule ~180 runs. With 16 concurrent runs allowed, 16 runs of that one DAG flood your workers, starving all other DAGs. Set this to 3–5 in production. Pair it with `catchup=False` for most DAGs, and enable catchup only for DAGs that are explicitly designed for historical backfill.

---

**Q9: How does the Airflow 3 standalone DAG processor improve performance?**

In Airflow 2, DAG parsing ran inside the scheduler process, competing for CPU with the scheduling loop. A slow import in one DAG file could block task scheduling for seconds. Airflow 3 allows `standalone_dag_processor = True`, which runs DAG parsing as a completely separate process (deployable as a separate container/pod). The scheduler process is now dedicated to evaluating task scheduling, while the DAG processor handles file I/O and Python imports. This separation means: (1) a misbehaving DAG file cannot block task scheduling, (2) each component can be independently scaled and resource-limited, (3) the scheduler loop becomes much more predictable.

---

**Q10: You have a DAG with 10,000 tasks generated via dynamic task mapping. What performance issues does this cause and how do you fix it?**

A 10,000-task mapping creates 10,000 task instance rows in the metadata DB for a single DAG run. This causes: (1) extremely slow DAG run page in the UI (loading/rendering 10,000 records), (2) scheduler taking much longer to evaluate the run, (3) large XCom payloads if each task pushes results, (4) `airflow db clean` taking longer. Fix by chunking: instead of mapping over 10,000 individual items, map over 100 chunks of 100 items each. Each mapped task processes a batch of 100 items internally, producing only 100 task instances. The processing is identical, but the database and scheduler overhead is reduced by 100x.
