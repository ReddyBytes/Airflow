# 16 — Dynamic Task Mapping: Cheatsheet

## expand() vs expand_kwargs() vs partial()

| Method | Input type | Use when |
|---|---|---|
| `expand(param=list)` | List of scalar values | You have one parameter that varies across a list |
| `expand(p1=list, p2=list)` | Two lists (cross-product) | You need every combination of two parameters |
| `expand_kwargs(list_of_dicts)` | List of dicts | Your inputs are naturally dict-shaped (e.g., from DB query) |
| `partial(p=val).expand(q=list)` | Fixed value + expanding list | Some params are constant, one varies |

---

## Syntax Reference

### Basic expand()
```python
@task
def process(item: str):
    ...

process.expand(item=["a", "b", "c"])         # static list
process.expand(item=upstream_task_result)     # XCom (dynamic)
```

### partial() + expand()
```python
process.partial(bucket="my-bucket", dry_run=False).expand(filename=file_list)
```

### expand_kwargs()
```python
@task
def load(table: str, schema: str):
    ...

load.expand_kwargs([
    {"table": "orders",    "schema": "raw"},
    {"table": "customers", "schema": "raw"},
])

# Or from XCom:
load.expand_kwargs(get_table_configs())
```

### Cross-product expand()
```python
@task
def run(region: str, env: str):
    ...

# 3 regions × 2 envs = 6 task instances
run.expand(region=["us", "eu", "ap"], env=["staging", "prod"])
```

---

## map_index Access

```python
# In @task decorated function
@task
def my_task(item: str, **context):
    idx = context["task_instance"].map_index
    print(f"Instance #{idx} processing: {item}")

# In Jinja template (traditional operators)
BashOperator(
    task_id="my_task",
    bash_command="echo 'Index: {{ task_instance.map_index }}'",
)
```

In the UI: mapped instances appear as `task_id[0]`, `task_id[1]`, `task_id[2]`...

---

## XCom Patterns with Mapped Tasks

### Map then reduce
```python
@task
def process(item: str) -> int:
    return len(item)

@task
def reduce(results: list[int]):   # receives ALL mapped outputs as a list
    return sum(results)

items = ["a", "bb", "ccc"]
mapped = process.expand(item=items)
reduce(mapped)                     # reduce gets [1, 2, 3]
```

### Dynamic list from upstream task
```python
@task
def list_items() -> list[str]:
    return fetch_from_s3()          # count not known at DAG write time

@task
def process(item: str):
    ...

items = list_items()
process.expand(item=items)          # task count determined at runtime
```

---

## Limitations Table

| Limitation | Detail |
|---|---|
| Input must be a list | `expand()` requires a list or XCom returning a list |
| All instances share config | Same `retries`, `retry_delay`, `pool` for all instances |
| No unique task IDs per instance | All share `task_id`, differentiated by `map_index` |
| Cross-product can be large | 10 lists × 10 items = 100 tasks — bound your inputs |
| `max_map_length` default | 1024 — configurable in `airflow.cfg` |

---

## Import Reference

```python
from airflow.decorators import task
# expand(), expand_kwargs(), partial() are methods on the @task result
# No separate imports needed for these methods
```

---

## Navigation

**Prev:** [15 — Task Groups](../15_Task_Groups/Cheatsheet.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [17 — Deferrable Operators](../17_Deferrable_Operators/Cheatsheet.md)
