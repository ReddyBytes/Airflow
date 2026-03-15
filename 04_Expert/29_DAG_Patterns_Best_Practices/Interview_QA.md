# 29 — DAG Patterns and Best Practices: Interview Q&A

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

**Q1: What is idempotency in the context of Airflow tasks, and why is it critical?**

An idempotent task produces exactly the same result whether it runs once or ten times — no duplicates, no errors from re-execution. It's critical because tasks fail and must be retried. In Airflow, retrying a failed task means re-running its `execute()` method from scratch. If the task appended data before failing, a retry will append it again — creating duplicates. Idempotent implementations use DELETE + INSERT (delete today's partition first, then insert), upsert (INSERT ON CONFLICT UPDATE), or overwrite semantics (always write to a deterministic S3 key that overwrites any existing file). Non-idempotent tasks appear to work fine until they fail and are retried.

---

**Q2: What is the DAG factory pattern and when should you use it?**

The DAG factory pattern generates multiple DAG objects programmatically in a single Python file using a loop over a configuration list. Instead of 20 nearly-identical files (`etl_orders.py`, `etl_customers.py`, etc.), one file with a `make_dag()` function and a `CONFIGS` list produces all 20 DAGs. Use it when: (1) you have 3+ DAGs with the same structure but different parameters, (2) a new "instance" requires only adding a config entry (no new Python file), (3) a bug fix or enhancement must apply to all instances simultaneously. The key constraint: the config list must be static (hardcoded or read from a YAML file at module level) — never from a database, which would reintroduce the top-level DB call anti-pattern.

---

**Q3: Why should you never use `datetime.now()` in task logic?**

`datetime.now()` returns the current wall-clock time when the task runs. When a task is retried an hour later, `datetime.now()` returns a different value — causing it to process a different time range than originally intended. When Airflow runs a backfill for a date 3 months ago, `datetime.now()` returns today — causing it to process today's data instead of the historical date. Both behaviors are incorrect. Always use `context["logical_date"]` (or `{{ logical_date }}` in templates, `{{ ds }}` for the date string) — this value is fixed for the DAG run, is the same on every retry, and represents the intended processing window for historical backfills.

---

**Q4: What is an atomic write and when does it matter in Airflow?**

An atomic write pattern ensures that output is either complete or absent — no partial state is ever visible. The technique: write to a temporary file path, then rename to the final path on success. On POSIX filesystems, `os.replace(tmp, final)` is an atomic syscall — no other process can observe a half-written state. This matters in Airflow because: (1) a task can be killed mid-write (OOM, Kubernetes pod eviction), (2) downstream sensors polling for the output file could start reading a partial file, (3) a task retry that partially overwrites an existing file creates corrupt data. On S3, writes are inherently atomic — an object either fully exists or doesn't.

---

**Q5: Why should you avoid top-level code in DAG files?**

Airflow's file processor re-imports every DAG file every `min_file_process_interval` seconds (default: 30s, recommended: 300s). Any Python at module level (outside of classes and functions) runs on every import. This means: `Variable.get()` makes a metadata DB call every 30 seconds per DAG file. `import pandas` adds 500ms to every parse cycle. A buggy DB connection string at module level crashes the file processor, preventing all DAGs in the file from loading. Move everything into functions: heavy imports, Variable/Connection access, database queries, API calls. Only static data structures (lists, dicts, strings) belong at module level.

---

**Q6: How do you design a DAG that is safe to backfill?**

A backfill-safe DAG: (1) uses `{{ ds }}` or `context["logical_date"]` instead of `datetime.now()` to determine what data to process, (2) is idempotent — running it again for a date that was already processed produces the same result without duplicates, (3) has `catchup=True` (or is explicitly called with `airflow dags backfill`), (4) has `max_active_runs_per_dag` set low enough to avoid overwhelming the target system during catchup, (5) respects `depends_on_past` only when sequential processing is genuinely required. A backfill of 90 days should produce identical results to running the DAG live for 90 days.

---

**Q7: What is the fan-out/fan-in pattern and what `trigger_rule` should the aggregation task use?**

Fan-out/fan-in processes N items in parallel (fan-out) and then aggregates results (fan-in). Implementation: a start task with N downstream tasks (one per item), all feeding into one final aggregation task. The aggregation task should use `trigger_rule="all_success"` if all items must succeed before aggregating, or `trigger_rule="all_done"` if you want to aggregate even partial results. Avoid `trigger_rule="one_success"` for fan-in — it fires the aggregation as soon as any one parallel task finishes, before the others complete. Dynamic Task Mapping is the modern Airflow 3 approach to fan-out: `task.expand(item=items_list)` auto-creates one mapped task instance per item.

---

**Q8: How do you version DAGs when making breaking changes?**

Breaking changes to a DAG (changing task IDs, removing tasks, changing schedule interval) can corrupt in-flight or recently-failed runs. The safe approach: create a new DAG with a version suffix (`dag_id="etl_orders_v2"`) rather than modifying the existing DAG. The old DAG continues to exist in the UI for historical reference (or is paused). New runs go to `etl_orders_v2`. After a period (e.g., when no runs of `etl_orders` are active), the old DAG can be paused or deleted. Non-breaking changes (adding a new task at the end, modifying a task's logic without changing its ID) can be made in place without versioning.

---

**Q9: What are XCom size limits and how do you handle large intermediate results?**

XCom values are stored in the metadata database as BLOB/JSONB. The size limit depends on the database (PostgreSQL JSONB: no hard limit but practically bad above 1MB; MySQL MEDIUMBLOB: 16MB). More importantly: large XCom values make the metadata DB grow rapidly, slow down the scheduler (which reads XCom for template rendering), and create performance problems. The rule of thumb: XCom is for small values (IDs, counts, URLs, status strings, small dicts). For anything larger — DataFrames, file contents, lists of thousands of items — write to S3/GCS and push the S3 URI as the XCom value. The downstream task reads from S3 using the URI.

---

**Q10: What should you include in a DAG's `doc_md` to make it production-ready?**

A production-quality `doc_md` should include: (1) **Purpose** — what the pipeline does in 1–2 sentences, (2) **Owner** — team name and Slack channel, (3) **Oncall/runbook** — link to a runbook or wiki page for when it fails at 3 AM, (4) **Schedule** — plain English description of when it runs (not just cron), (5) **Dependencies** — what upstream data or systems it depends on, (6) **Outputs** — what tables, files, or systems it writes to, (7) **Failure guidance** — common failure modes and how to resolve them, (8) **Changelog** — brief history of major changes. A new team member should be able to debug a failure in this DAG at midnight using only the `doc_md`, without asking anyone.
