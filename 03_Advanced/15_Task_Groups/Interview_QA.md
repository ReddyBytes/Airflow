# 15 — Task Groups: Interview Q&A

---

**Q1. What is a TaskGroup in Airflow 3 and what problem does it solve?**

A `TaskGroup` is a context manager that groups related tasks together into a collapsible visual container in the Airflow UI. It solves the readability problem that comes with large DAGs — when you have 20+ tasks, the graph view becomes hard to navigate. TaskGroup lets you organize tasks by logical stage (Extract, Transform, Load) so operators can see the pipeline structure at a glance, collapse groups they don't care about, and drill into groups they're debugging.

---

**Q2. Why were SubDAGs removed in Airflow 3?**

SubDAGs had multiple serious production issues: they caused deadlocks when the pool was full (the SubDagOperator occupies a pool slot while the child tasks also need pool slots), they created confusing double-DAG semantics (a SubDAG had its own separate DAG run and history), they added scheduler overhead (every SubDAG was a fully parsed DAG object), and they were difficult to debug because you couldn't see inside a SubDAG from the parent graph. `TaskGroup` solves all of these problems — it is a pure UI/organizational concept with no runtime overhead and no pool slot issues.

---

**Q3. How do you define a TaskGroup?**

Use it as a context manager with `with TaskGroup("name") as group_var:`. All tasks defined inside the block belong to the group. You then set dependencies on `group_var` just like a normal task:

```python
with TaskGroup("extract") as extract:
    pull_a = PythonOperator(task_id="pull_a", ...)
    pull_b = PythonOperator(task_id="pull_b", ...)

extract >> transform_task
```

---

**Q4. How are task IDs affected by TaskGroup membership?**

By default, task IDs inside a group are prefixed with the group name, separated by a dot: `group_name.task_id`. For example, a task with `task_id="pull_api"` inside `TaskGroup("extract")` gets the full ID `extract.pull_api`. This namespacing prevents collisions when the same task name appears in multiple groups.

---

**Q5. How do you create nested TaskGroups?**

Simply nest the `with TaskGroup(...)` context managers:

```python
with TaskGroup("processing") as processing:
    with TaskGroup("validate") as validate:
        check = PythonOperator(task_id="check", ...)
    with TaskGroup("transform") as transform:
        apply = PythonOperator(task_id="apply", ...)
    validate >> transform
```

Nested task IDs follow the full path: `processing.validate.check`, `processing.transform.apply`.

---

**Q6. What does prefix_group_id=False do and when should you use it?**

Setting `prefix_group_id=False` disables the automatic task ID prefix, so tasks keep their bare `task_id` without the group name prepended. This is rarely recommended because it removes the namespacing protection — if two groups contain a task with the same `task_id`, you get a collision error. Only use it when you have a specific need and can guarantee all task IDs across all groups are globally unique.

---

**Q7. Can you set dependencies between two TaskGroups?**

Yes. The group variable returned by `with TaskGroup(...) as group:` behaves like a task for dependency purposes. You can use `>>` between group variables, and Airflow will wire all the entry/exit tasks of each group appropriately:

```python
with TaskGroup("extract")   as extract:   ...
with TaskGroup("transform") as transform: ...
with TaskGroup("load")      as load:      ...

extract >> transform >> load
```

---

**Q8. What is the difference between TaskGroup and a SubDAG in terms of runtime behavior?**

`TaskGroup` has **no runtime impact at all**. Tasks inside a group run as ordinary tasks on your workers — the group is purely a UI and code organization concept. A SubDAG, in contrast, used a `SubDagOperator` that occupied a worker slot and spawned a separate DAG execution context. This extra indirection caused pool deadlocks and double-state confusion. Since SubDAGs are removed in Airflow 3, there is no longer a "heavier" grouping alternative — TaskGroup is the only option, and it is the right option.

---

## Navigation

**Prev:** [14 — Branching and Control Flow](../14_Branching_and_Control_Flow/Interview_QA.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [16 — Dynamic Task Mapping](../16_Dynamic_Task_Mapping/Interview_QA.md)
