# 16 — Dynamic Task Mapping: Interview Q&A

---

**Q1. What is dynamic task mapping in Airflow 3?**

Dynamic task mapping allows you to create a variable number of task instances at runtime based on actual data — not at DAG parse time. You call `expand()` on a task's parameter with a list (or an XCom result that produces a list), and Airflow creates one task instance per item in that list when the DAG executes. This solves the common problem of needing one task per file, one task per customer, or one task per any unknown-at-write-time collection.

---

**Q2. What is the difference between expand() and partial()?**

`expand()` is the expansion mechanism — you pass a list and Airflow creates one task per item. `partial()` is used to "pin" fixed parameters before calling `expand()`. When your task has multiple parameters but only one varies, use `partial()` to set the constants and then `expand()` for the one that changes:

```python
process.partial(output_bucket="my-bucket", compress=True).expand(filename=file_list)
```

`partial()` alone does nothing — it must be followed by `.expand()`.

---

**Q3. What is expand_kwargs() and when would you use it?**

`expand_kwargs()` accepts a list of dictionaries instead of a single list of values. Use it when your input is naturally structured as records — for example, rows from a database query where each row has multiple columns that map to different task parameters:

```python
load.expand_kwargs([
    {"table": "orders",    "schema": "raw", "truncate": True},
    {"table": "customers", "schema": "raw", "truncate": False},
])
```

This creates two task instances, each with a different set of argument values.

---

**Q4. What is map_index and how do you access it?**

`map_index` is the zero-based integer identifier for each mapped task instance. The first instance is `map_index=0`, the second is `map_index=1`, and so on. In the Airflow UI, mapped instances appear as `task_id[0]`, `task_id[1]`, etc. You access it in code via `context["task_instance"].map_index` inside a `@task`-decorated function.

---

**Q5. How does XCom work with mapped tasks?**

Each mapped task instance can push an XCom value normally. When a downstream task pulls from a mapped task's XCom, it receives a **list** containing all the mapped instances' values in order by `map_index`. This enables the classic "map then reduce" pattern: map your work across N tasks, then reduce the results in a single downstream task that receives all N outputs as a Python list.

---

**Q6. How do you create a cross-product mapping?**

Pass multiple parameters to `expand()`. Airflow creates one task for every combination of values:

```python
train.expand(
    algorithm=["rf", "xgb"],
    learning_rate=[0.01, 0.1],
)
# Creates 4 tasks: (rf, 0.01), (rf, 0.1), (xgb, 0.01), (xgb, 0.1)
```

Be careful with large inputs — the task count grows multiplicatively.

---

**Q7. How do you filter which mapped tasks are created?**

Use `None` return values to signal that a mapped instance should be skipped. Create an intermediate task that returns `None` for items that should be excluded, and only chain the downstream processing task to the non-None results. Alternatively, filter the input list before passing it to `expand()` — a smaller list means fewer tasks.

---

**Q8. Can you chain two mapped tasks together?**

Yes. When you chain mapped tasks, Airflow pairs them 1:1 by `map_index`. Mapped instance 0 of the upstream feeds into mapped instance 0 of the downstream, instance 1 to instance 1, and so on. The number of downstream instances matches the number of upstream instances:

```python
raw  = extract.expand(source=sources)        # N instances
proc = transform.expand(data=raw)            # N instances, paired 1:1
load.expand(processed=proc)                  # N instances, paired 1:1
```

---

**Q9. What are the key limitations of dynamic task mapping?**

- The input to `expand()` must be a list or an XCom that returns a list — generators are not supported.
- All mapped instances share the same task configuration (`retries`, `retry_delay`, `pool`, etc.) — you cannot configure individual instances differently.
- There is no unique `task_id` per instance — they all share the same ID, differentiated only by `map_index`.
- Cross-product mapping can create a very large number of tasks quickly — always bound your input lists.
- The default `max_map_length` is 1024; this is configurable but exists to prevent runaway task generation.

---

**Q10. What is the difference between dynamic task mapping and creating tasks in a loop at parse time?**

A parse-time loop (like `for item in hardcoded_list: MyOperator(task_id=...)`) generates tasks when Airflow loads the DAG file. The task count is fixed based on what the code evaluates to at parse time. Dynamic task mapping (`expand()`) generates task instances when the DAG **runs** — the count is determined by data that only exists at runtime (e.g., the result of an API call or S3 listing). Dynamic mapping also integrates natively with the scheduler and UI, showing proper mapped instance tracking and XCom aggregation.

---

## Navigation

**Prev:** [15 — Task Groups](../15_Task_Groups/Interview_QA.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [17 — Deferrable Operators](../17_Deferrable_Operators/Interview_QA.md)
