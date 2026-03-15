# 23 — Plugins and Customization: Cheatsheet

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## AirflowPlugin Attributes

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | **Required.** Unique plugin identifier |
| `operators` | `list[type]` | Custom BaseOperator subclasses |
| `sensors` | `list[type]` | Custom BaseSensorOperator subclasses |
| `hooks` | `list[type]` | Custom BaseHook subclasses |
| `macros` | `list[callable]` | Functions exposed in Jinja templates |
| `flask_blueprints` | `list[Blueprint]` | Flask Blueprint objects for new routes |
| `appbuilder_views` | `list[dict]` | Dicts with `{"view": ViewInstance}` |
| `appbuilder_menu_items` | `list[dict]` | Dicts with `name`, `category`, `href` |
| `timetables` | `list[type]` | Custom Timetable subclasses |
| `listeners` | `list[object]` | Objects with `@hookimpl` methods |

---

## Plugin Types with Minimal Syntax

### Macro Plugin
```python
from airflow.plugins_manager import AirflowPlugin

def my_macro(value: str) -> str:
    return value.upper()

class MyPlugin(AirflowPlugin):
    name = "my_plugin"
    macros = [my_macro]

# Usage in DAG template:
# {{ macros.my_plugin.my_macro(some_var) }}
```

### Flask Blueprint Plugin
```python
from flask import Blueprint
from airflow.plugins_manager import AirflowPlugin

bp = Blueprint("my_bp", __name__, url_prefix="/my_bp")

@bp.route("/hello")
def hello():
    return "Hello from plugin!"

class MyPlugin(AirflowPlugin):
    name = "my_plugin"
    flask_blueprints = [bp]
```

### AppBuilderBaseView Plugin
```python
from flask_appbuilder import expose, BaseView as AppBuilderBaseView
from airflow.plugins_manager import AirflowPlugin

class MyView(AppBuilderBaseView):
    default_view = "index"

    @expose("/")
    def index(self):
        return self.render_template("my_template.html")

class MyPlugin(AirflowPlugin):
    name = "my_plugin"
    appbuilder_views = [{"view": MyView()}]
    appbuilder_menu_items = [{
        "name": "My Page",
        "category": "My Category",
        "category_icon": "fa-star",
        "href": "/myview/",
    }]
```

### Listener Plugin
```python
from airflow.listeners import hookimpl
from airflow.plugins_manager import AirflowPlugin

class MyListener:
    @hookimpl
    def on_task_instance_failed(self, previous_state, task_instance, session):
        print(f"FAILED: {task_instance.dag_id}.{task_instance.task_id}")

class MyPlugin(AirflowPlugin):
    name = "my_plugin"
    listeners = [MyListener()]
```

### Timetable Plugin
```python
from airflow.timetables.base import Timetable
from airflow.plugins_manager import AirflowPlugin

class MyTimetable(Timetable):
    # implement next_dagrun_info(), infer_manual_data_interval()
    ...

class MyPlugin(AirflowPlugin):
    name = "my_plugin"
    timetables = [MyTimetable]
```

---

## Plugin Discovery Methods

| Method | Location | Best For |
|---|---|---|
| `plugins/` folder | `$AIRFLOW_HOME/plugins/*.py` | Quick local development |
| Entry points | `pyproject.toml` `[project.entry-points."airflow.plugins"]` | Team distribution via pip |
| Direct import | Regular Python package | When you don't need plugin registration |

### Entry Point Declaration
```toml
# pyproject.toml
[project.entry-points."airflow.plugins"]
my_plugin = "my_package.plugin:MyPlugin"
```

### Verify Loaded Plugins
```bash
airflow plugins list
```

---

## Listeners Hook Points

| Hook Method | Signature | Event |
|---|---|---|
| `on_task_instance_running` | `(previous_state, task_instance, session)` | Task → RUNNING |
| `on_task_instance_success` | `(previous_state, task_instance, session)` | Task → SUCCESS |
| `on_task_instance_failed` | `(previous_state, task_instance, session)` | Task → FAILED |
| `on_dag_run_running` | `(dag_run, msg, session)` | DAG Run → RUNNING |
| `on_dag_run_success` | `(dag_run, msg, session)` | DAG Run → SUCCESS |
| `on_dag_run_failed` | `(dag_run, msg, session)` | DAG Run → FAILED |

All methods are optional — implement only the hooks you need.

---

## Lazy Loading Config

```ini
# airflow.cfg
[core]
lazy_load_plugins = True   # default in Airflow 3, faster startup
```

Set to `False` only if your plugin must execute code at import time (rare).

---

## Menu Item Dict Schema
```python
{
    "name": "Page Title",          # menu item label
    "category": "Category Name",   # dropdown category in nav bar
    "category_icon": "fa-bolt",    # Font Awesome icon class
    "href": "/myview/",            # URL path
}
```
