# 23 — Plugins and Customization: Interview Q&A

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

**Q1: What is an Airflow plugin and what problem does it solve?**

An Airflow plugin is a Python class that inherits from `AirflowPlugin` and extends Airflow's functionality without modifying the core codebase. It solves the "platform extensibility" problem: enterprise teams need custom UI pages, company-specific Jinja macros, proprietary operators, custom schedules, and platform-wide observability hooks — all of which can be delivered as plugins. The plugin system provides stable integration points that survive Airflow version upgrades.

---

**Q2: How are plugins discovered and loaded in Airflow 3?**

Airflow 3 discovers plugins through two mechanisms: (1) scanning all `.py` files in `$AIRFLOW_HOME/plugins/` at startup, and (2) reading Python package entry points declared under the `"airflow.plugins"` group in `pyproject.toml` or `setup.cfg`. By default, Airflow 3 uses lazy loading (`lazy_load_plugins = True`), meaning plugins are not imported until needed. You can verify loaded plugins with `airflow plugins list`.

---

**Q3: What are all the things you can extend through a plugin?**

Through an `AirflowPlugin` you can register: custom Operators, Sensors, and Hooks (for legacy compat or discoverability); Jinja macros available in all DAG templates; Flask Blueprints that add new routes to the web application; `AppBuilderBaseView` subclasses that add full UI pages with navigation menu entries; custom Timetable classes for non-standard schedules; and Listener objects that hook into the task/DAG lifecycle. In Airflow 3, Timetables and Listeners are the most commonly needed plugin types.

---

**Q4: How do you create a custom Jinja macro accessible in all DAGs?**

Define a plain Python function, include it in a plugin's `macros` list, and drop the file in `plugins/`. The function becomes available in templates as `{{ macros.<plugin_name>.<function_name>(args) }}`. For example, a plugin named `"date_macros"` with a function `format_ds` is called as `{{ macros.date_macros.format_ds(ds, '%Y/%m/%d') }}`. No per-DAG configuration is needed — the macro is globally available as soon as the plugin is loaded.

---

**Q5: What is an AppBuilderBaseView and when would you use one?**

`AppBuilderBaseView` is a Flask-AppBuilder view class that integrates a new web page directly into the Airflow UI with the same look and feel (navigation bar, styling). You subclass it, decorate methods with `@expose("/path")`, render templates that extend `airflow/main.html`, and register it via `appbuilder_views` in your plugin. Use cases include: compliance audit dashboards that query the metadata DB, data lineage visualization pages, custom monitoring views, team-specific reporting pages embedded inside the Airflow UI.

---

**Q6: What are listeners and how do they differ from task callbacks?**

Listeners (introduced Airflow 2.4, expanded in Airflow 3) are objects with `@hookimpl`-decorated methods that fire on task and DAG run state transitions for the entire Airflow installation. Task callbacks (`on_failure_callback`, `on_success_callback`) are Python callables attached to individual tasks or DAGs. The key difference is scope: a single listener fires for every task everywhere, while callbacks must be added to every task individually. Listeners are the correct Airflow 3 approach to platform-wide concerns like audit logging, alerting, and metrics emission.

---

**Q7: How do you implement a listener that fires only on task failures?**

```python
from airflow.listeners import hookimpl
from airflow.plugins_manager import AirflowPlugin

class FailureListener:
    @hookimpl
    def on_task_instance_failed(self, previous_state, task_instance, session):
        # task_instance has .dag_id, .task_id, .run_id, .duration, etc.
        send_pagerduty_alert(task_instance.dag_id, task_instance.task_id)

class MyPlugin(AirflowPlugin):
    name = "failure_alerting"
    listeners = [FailureListener()]
```

Only implement the hooks you need — `@hookimpl` methods are opt-in. The `session` parameter is a live SQLAlchemy session you can use to query the metadata DB within the hook.

---

**Q8: What is the recommended way to distribute plugins across multiple Airflow deployments?**

The recommended approach is to package the plugin as a pip-installable Python package and declare it under `[project.entry-points."airflow.plugins"]` in `pyproject.toml`. This gives you: version control, changelog, automated testing in CI, distribution via a private PyPI server, and clean upgrade paths. The `plugins/` folder approach is appropriate for local development and single-cluster deployments where a full packaging workflow is overhead. Entry point-based plugins are also eager-loaded, avoiding lazy-loading edge cases.

---

**Q9: Can a plugin have security implications? How do you restrict access to custom UI pages?**

Yes. `AppBuilderBaseView` pages are accessible to any authenticated user by default. To add role-based access control, use Flask-AppBuilder's `@has_access` decorator or define `base_permissions` on the view class. For example:

```python
from airflow.www.auth import has_access
from flask_appbuilder.security.decorators import has_access as fab_has_access

class MyView(AppBuilderBaseView):
    @expose("/")
    @has_access([(permissions.ACTION_CAN_READ, permissions.RESOURCE_DAG)])
    def index(self):
        ...
```

Always apply access control to custom pages, especially those that query or expose metadata DB data.

---

**Q10: How does lazy loading affect plugin behavior and when should you disable it?**

With `lazy_load_plugins = True` (Airflow 3 default), plugins are not imported at Airflow startup — they are loaded on first use. This dramatically reduces startup time when you have many or heavyweight plugins. The consequence is that any code at module level in your plugin file does not run at startup. Disable lazy loading (`lazy_load_plugins = False`) only when your plugin must execute initialization code at startup — for example, to register a custom connection type with the connection form UI, or to install signal handlers. The cost is increased scheduler/webserver startup time.
