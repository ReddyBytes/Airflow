# 24 — Custom Operators and Hooks: Cheatsheet

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## BaseOperator Interface

| Method / Attribute | Required | Description |
|---|---|---|
| `execute(self, context)` | **Yes** | Main execution logic. Return value → XCom |
| `template_fields` | Recommended | Tuple of attr names to Jinja-render |
| `template_ext` | Optional | File extensions for file-based templates (`.sql`, `.json`) |
| `ui_color` | Optional | Hex color for Graph view task node background |
| `ui_fgcolor` | Optional | Hex color for Graph view task node text |
| `__init__(self, ..., **kwargs)` | **Yes** | Must call `super().__init__(**kwargs)` |

### BaseOperator Key `__init__` Parameters (forwarded via `**kwargs`)

| Parameter | Default | Description |
|---|---|---|
| `task_id` | **Required** | Unique task identifier within a DAG |
| `retries` | `0` | Number of retry attempts |
| `retry_delay` | `timedelta(seconds=300)` | Delay between retries |
| `retry_exponential_backoff` | `False` | Exponential backoff between retries |
| `execution_timeout` | `None` | Max task duration before timeout |
| `on_failure_callback` | `None` | Callable called on failure |
| `on_success_callback` | `None` | Callable called on success |
| `trigger_rule` | `"all_success"` | When task should be triggered |
| `pool` | `None` | Pool for concurrency control |
| `priority_weight` | `1` | Scheduler priority |
| `queue` | `"default"` | Celery queue |
| `doc_md` | `None` | Markdown documentation for task |

---

## BaseSensorOperator Interface

| Method / Attribute | Required | Description |
|---|---|---|
| `poke(self, context)` | **Yes** | Returns `True` (done) or `False` (keep waiting) |
| `poke_interval` | `60` | Seconds between pokes |
| `timeout` | `7 * 24 * 3600` | Fail after this many seconds |
| `mode` | `"poke"` | `"poke"`, `"reschedule"`, or `"deferrable"` |
| `soft_fail` | `False` | Mark SKIPPED instead of FAILED on timeout |
| `exponential_backoff` | `False` | Grow poke_interval exponentially |

### Sensor Mode Comparison

| Mode | Worker Slot | Scales Well | Use Case |
|---|---|---|---|
| `poke` | Held during wait | No | Short waits (<5 min) |
| `reschedule` | Released between pokes | Yes | Long waits, production |
| Deferrable | Released entirely | Best | Kubernetes/ECS, async triggers |

---

## BaseHook Interface

| Method / Attribute | Required | Description |
|---|---|---|
| `get_conn(self)` | **Yes** | Returns connection object (cache with `self._conn`) |
| `conn_name_attr` | Recommended | String: attribute name for `conn_id` param |
| `default_conn_name` | Recommended | Default connection ID string |
| `conn_type` | Recommended | Shows in UI connection type dropdown |
| `hook_name` | Recommended | Display name in UI |
| `get_connection(conn_id)` | Inherited | Fetches `Connection` from secrets backend |

### Connection Object Attributes

```python
conn = self.get_connection(self.conn_id)
conn.host        # hostname
conn.port        # int port
conn.login       # username
conn.password    # password (decrypted)
conn.schema      # database name or path
conn.conn_type   # connection type string
conn.extra       # raw extra JSON string
conn.extra_dejson  # extra parsed as dict
```

---

## template_fields Quick Reference

```python
class MyOperator(BaseOperator):
    # These fields will have {{ }} expressions resolved before execute()
    template_fields = ("sql", "s3_key", "table_name")
    template_ext = (".sql",)  # if sql is a filepath, render file contents too

    def __init__(self, sql: str, s3_key: str, table_name: str, **kwargs):
        super().__init__(**kwargs)
        self.sql = sql
        self.s3_key = s3_key
        self.table_name = table_name
```

**Rule:** Include every string attribute that a DAG author might reasonably want to parameterize.

---

## ui_color Options (Common Choices)

| Color | Hex | Visual Use |
|---|---|---|
| Blue | `#4a9eff` | Data loading operators |
| Green | `#00c853` | Success/validation operators |
| Orange | `#ff6d00` | Transform operators |
| Purple | `#7b1fa2` | ML/AI operators |
| Teal | `#00897b` | Streaming operators |
| Pink | `#e91e63` | Alerting operators |
| Default (light blue) | `#fff` | Airflow built-in default |

---

## Minimal Operator Template

```python
from airflow.models import BaseOperator
from airflow.utils.context import Context


class MyOperator(BaseOperator):
    template_fields = ("my_param",)
    ui_color = "#4a9eff"

    def __init__(self, my_param: str, **kwargs):
        super().__init__(**kwargs)
        self.my_param = my_param

    def execute(self, context: Context):
        self.log.info("Running with param: %s", self.my_param)
        result = do_something(self.my_param)
        return result  # pushed to XCom automatically
```

---

## Minimal Hook Template

```python
from airflow.hooks.base import BaseHook


class MyHook(BaseHook):
    conn_name_attr = "my_conn_id"
    default_conn_name = "my_default"
    conn_type = "my_system"
    hook_name = "My System"

    def __init__(self, conn_id: str = default_conn_name):
        super().__init__()
        self.conn_id = conn_id
        self._conn = None

    def get_conn(self):
        if self._conn is None:
            conn = self.get_connection(self.conn_id)
            self._conn = MyClient(
                host=conn.host,
                user=conn.login,
                password=conn.password,
            )
        return self._conn
```

---

## Minimal Sensor Template

```python
from airflow.sensors.base import BaseSensorOperator
from airflow.utils.context import Context


class MySensor(BaseSensorOperator):
    template_fields = ("target",)

    def __init__(self, target: str, **kwargs):
        super().__init__(**kwargs)
        self.target = target

    def poke(self, context: Context) -> bool:
        result = check_condition(self.target)
        self.log.info("Condition met: %s", result)
        return result
```

---

## Packaging Checklist

- [ ] `__init__.py` in every package directory
- [ ] `template_fields` declared for all parameterized string attributes
- [ ] `**kwargs` passed to `super().__init__()`
- [ ] Hook credentials read from `get_connection()` — never hardcoded
- [ ] Sensor uses `mode="reschedule"` for production use
- [ ] Unit tests mock the hook layer (no real network calls in tests)
- [ ] `pyproject.toml` with correct `apache-airflow>=3.0.0` dependency
- [ ] Entry point declared if distributing as pip package
- [ ] Version pinned and changelog maintained
- [ ] `execute()` returns a serializable value (str, int, dict, list) for XCom
