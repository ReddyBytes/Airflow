# 15 — Task Groups: Cheatsheet

## Basic TaskGroup Syntax

```python
from airflow.utils.task_group import TaskGroup

with TaskGroup("group_name") as my_group:
    task_a = SomeOperator(task_id="task_a", ...)
    task_b = SomeOperator(task_id="task_b", ...)
    task_a >> task_b

# Set dependencies on the whole group
upstream_task >> my_group >> downstream_task
```

---

## Nested TaskGroup Syntax

```python
with TaskGroup("outer") as outer:
    with TaskGroup("inner_a") as inner_a:
        t1 = SomeOperator(task_id="t1", ...)
    with TaskGroup("inner_b") as inner_b:
        t2 = SomeOperator(task_id="t2", ...)
    inner_a >> inner_b

# Task IDs: outer.inner_a.t1, outer.inner_b.t2
```

---

## prefix_group_id Parameter

| Value | Task ID result | When to use |
|---|---|---|
| `True` (default) | `group_name.task_id` | Always — prevents ID collisions |
| `False` | `task_id` (no prefix) | Only if you have a specific need and IDs are unique across all groups |

```python
with TaskGroup("my_group", prefix_group_id=False) as g:
    t = SomeOperator(task_id="my_task", ...)
# task_id = "my_task" (no prefix)
```

---

## TaskGroup vs SubDAG (Airflow 3)

| Aspect | TaskGroup | SubDAG |
|---|---|---|
| Available in Airflow 3 | Yes | **No — removed** |
| Separate DAG file needed | No | Yes |
| Deadlock risk | No | Yes (pool exhaustion) |
| Scheduler overhead | None | Extra DAG load |
| UI visibility | Inline, collapsible | Separate page |
| Code complexity | Simple context manager | Required factory function |
| Pool slots used | Per-task (normal) | Extra slot for SubDagOperator |

---

## Common Patterns

### ETL Stage Groups
```python
with TaskGroup("extract")   as extract:   ...
with TaskGroup("transform") as transform: ...
with TaskGroup("load")      as load:      ...

extract >> transform >> load
```

### Group with Internal Dependencies
```python
with TaskGroup("process") as process:
    step1 = PythonOperator(task_id="step1", ...)
    step2 = PythonOperator(task_id="step2", ...)
    step3 = PythonOperator(task_id="step3", ...)
    step1 >> [step2, step3]
```

### Reusable Group Factory
```python
def make_source_group(source_name: str) -> TaskGroup:
    with TaskGroup(f"process_{source_name}") as group:
        fetch    = PythonOperator(task_id="fetch",    ...)
        validate = PythonOperator(task_id="validate", ...)
        load     = PythonOperator(task_id="load",     ...)
        fetch >> validate >> load
    return group

crm_group  = make_source_group("crm")
erp_group  = make_source_group("erp")
[crm_group, erp_group] >> merge_task
```

---

## Import Reference

```python
from airflow.utils.task_group import TaskGroup
```

---

## Navigation

**Prev:** [14 — Branching and Control Flow](../14_Branching_and_Control_Flow/Cheatsheet.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [16 — Dynamic Task Mapping](../16_Dynamic_Task_Mapping/Cheatsheet.md)
