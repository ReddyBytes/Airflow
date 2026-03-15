# 10 — Branching and Control Flow: Cheatsheet

## TriggerRule Types

| TriggerRule | Constant | Task runs when... | Typical use case |
|---|---|---|---|
| `ALL_SUCCESS` | `TriggerRule.ALL_SUCCESS` | All parents succeeded | Normal pipeline step (default) |
| `ALL_FAILED` | `TriggerRule.ALL_FAILED` | All parents failed | Last-resort fallback handler |
| `ALL_DONE` | `TriggerRule.ALL_DONE` | All parents finished (any state) | Cleanup / teardown task |
| `ONE_SUCCESS` | `TriggerRule.ONE_SUCCESS` | At least one parent succeeded | Fan-in race |
| `ONE_FAILED` | `TriggerRule.ONE_FAILED` | At least one parent failed | Immediate failure alert |
| `NONE_FAILED` | `TriggerRule.NONE_FAILED` | No parent failed (skipped is OK) | Join task after a branch |
| `NONE_FAILED_MIN_ONE_SUCCESS` | `TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS` | No failure AND at least one success | Strict join after a branch |
| `NONE_SKIPPED` | `TriggerRule.NONE_SKIPPED` | No parent was skipped | Must-run task in a critical path |

---

## BranchPythonOperator

```python
from airflow.operators.python import BranchPythonOperator

def choose_branch():
    # Must return a task_id string (or list of task_id strings)
    if some_condition():
        return "task_id_a"
    return "task_id_b"

branch_task = BranchPythonOperator(
    task_id="decide",
    python_callable=choose_branch,
)

# Multiple branches
def choose_multiple():
    return ["notify_slack", "update_dashboard"]

# Set trigger_rule on any join task downstream of both branches
join_task = SomeOperator(
    task_id="join",
    trigger_rule="none_failed",  # don't skip just because one branch was skipped
)
```

---

## ShortCircuitOperator

```python
from airflow.operators.python import ShortCircuitOperator

def is_condition_met(**context):
    # Return True to continue, False to skip ALL downstream tasks
    return True  # or False

gate = ShortCircuitOperator(
    task_id="my_gate",
    python_callable=is_condition_met,
    # ignore_downstream_trigger_rules=True (default) — skips ALL downstream
    # ignore_downstream_trigger_rules=False — only skips immediate children
)

gate >> downstream_task_a >> downstream_task_b
```

---

## BranchPythonOperator vs ShortCircuitOperator

| Aspect | BranchPythonOperator | ShortCircuitOperator |
|---|---|---|
| Return type | `str` or `list[str]` (task IDs) | `bool` |
| Non-chosen tasks | SKIPPED | SKIPPED |
| Alternative path | Yes — other branch runs | No — everything downstream is skipped |
| Use for | Routing between paths | Stop-or-continue gate |

---

## Common Branching Patterns

### Pattern 1 — Quality Gate
```python
ShortCircuitOperator(task_id="check_quality", python_callable=lambda: rows > 0)
```

### Pattern 2 — Environment Routing
```python
def route_by_env():
    env = Variable.get("environment")
    return f"load_{env}"  # "load_prod" or "load_staging"
```

### Pattern 3 — Conditional Alert on Any Failure
```python
alert_task = EmailOperator(
    task_id="send_failure_alert",
    trigger_rule="one_failed",
    ...
)
[task_a, task_b, task_c] >> alert_task
```

### Pattern 4 — Day-of-Week Gate
```python
def is_weekday(**context):
    return context["execution_date"].isoweekday() <= 5

ShortCircuitOperator(task_id="weekday_only", python_callable=is_weekday)
```

---

## Import Reference

```python
from airflow.operators.python import BranchPythonOperator, ShortCircuitOperator
from airflow.utils.trigger_rule import TriggerRule

# Use TriggerRule constants (avoids typos)
task = SomeOperator(trigger_rule=TriggerRule.NONE_FAILED)
task = SomeOperator(trigger_rule=TriggerRule.ONE_FAILED)
task = SomeOperator(trigger_rule=TriggerRule.ALL_DONE)
```
