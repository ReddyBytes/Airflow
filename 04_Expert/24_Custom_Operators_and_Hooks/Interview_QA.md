# 24 — Custom Operators and Hooks: Interview Q&A

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

**Q1: When should you build a custom operator instead of using an existing one?**

Build a custom operator when: (1) no provider package exists for your system, (2) an existing operator doesn't expose the parameters you need, (3) you need to compose multiple API calls into a single logical task, or (4) you want to enforce company standards (naming conventions, auth, error handling) across all DAG authors. Avoid building custom operators when a combination of existing operators (especially `PythonOperator`) would be cleaner and equally maintainable. A custom operator is justified when the same pattern appears in 3+ DAGs.

---

**Q2: What method must you implement in a BaseOperator subclass, and what does it receive?**

You must implement `execute(self, context: Context) -> Any`. The `context` parameter is a dictionary containing everything available in Jinja templates: `ds` (execution date string), `logical_date` (datetime), `dag` (DAG object), `task` (Task object), `task_instance` (TaskInstance object), `conf` (DAG run conf), `params` (DAG params), `var.value` (Variables accessor), `conn` (Connections accessor), and more. The return value of `execute()` is automatically pushed to XCom.

---

**Q3: What is `template_fields` and why is it important?**

`template_fields` is a class-level tuple of attribute names that Airflow renders as Jinja templates before calling `execute()`. Without it, expressions like `"SELECT * FROM {{ ds }}"` are passed as literal strings. With it, the template is resolved at runtime with the actual execution date. Any string attribute that a DAG author might want to parameterize (SQL queries, file paths, table names, API endpoints) should be included. If you forget `template_fields`, users get `{{ ds }}` literally in their SQL — a hard-to-debug issue.

---

**Q4: How do you pass credentials securely to a custom hook?**

Always use `self.get_connection(self.conn_id)` inherited from `BaseHook`. This queries the configured secrets backend (Vault, AWS Secrets Manager, environment variables) and returns an `airflow.models.Connection` object with decrypted `host`, `login`, `password`, `port`, `schema`, and `extra` fields. Never hardcode credentials or read them from environment variables directly in hook code. This pattern ensures the same hook code works across dev/staging/prod without modification — only the connection object differs.

---

**Q5: What is the difference between `poke`, `reschedule`, and deferrable sensor modes?**

In `poke` mode, the worker process sleeps between checks — it holds a worker slot for the entire duration of the wait. In `reschedule` mode, the task is set to `up_for_reschedule` state between pokes, releasing the worker slot; the scheduler re-queues it after `poke_interval`. In deferrable mode, the task suspends entirely via a `Trigger` and an async I/O loop wakes it up when the condition is met — it uses no worker slots at all. For production, use `reschedule` at minimum; use deferrable for long-running conditions or when running on Kubernetes with auto-scaling.

---

**Q6: How do you test a custom operator without making real API calls?**

Use `unittest.mock.patch` to replace the hook class with a `MagicMock`. Configure the mock to return predictable values from `submit_job()`, `get_job_status()`, etc. Call `operator.execute(context={})` directly — no DAG, no Airflow database needed. Set `poll_interval=0` in the operator constructor to skip `time.sleep()` calls. Test both the success path and failure paths (mock returning `"FAILED"` status should raise `AirflowException`). This gives fast, deterministic unit tests in CI without any external dependencies.

---

**Q7: How do you package a custom operator for distribution across multiple teams?**

Create a standard Python package with `pyproject.toml` declaring `apache-airflow>=3.0.0` as a dependency. Organize it as `airflow_mycompany/operators/`, `airflow_mycompany/hooks/`, `airflow_mycompany/sensors/`. If you want Airflow to show the hook in the UI connections form, add an `AirflowPlugin` via an entry point. Publish to a private PyPI server (Artifactory, CodeArtifact, Nexus). Pin the version in each Airflow environment's `requirements.txt`. Teams install with `pip install airflow-mycompany==1.2.0` and import normally.

---

**Q8: What happens if `execute()` raises an exception?**

Airflow catches the exception, marks the task instance as `FAILED`, and records the traceback in the task log. If `retries > 0`, the scheduler re-queues the task after `retry_delay`. If the exception is `AirflowSkipException`, the task is marked `SKIPPED` instead. If you need to mark downstream tasks as failed without retrying, raise `AirflowException` directly. For expected "soft" failures (e.g., no data available), raise `AirflowSkipException` so downstream tasks can proceed or be skipped based on `trigger_rule`.

---

**Q9: How do you make a custom operator's state visible in the Airflow UI?**

Use `self.log.info()` (from the inherited `self.log` logger) to emit progress information — it appears in the task log viewable in the Airflow UI. For longer operations, log progress updates periodically. Use `ui_color` and `ui_fgcolor` to make your operator visually distinct in the Graph view. Provide a meaningful `doc_md` on the task instance to explain what the operator does. If the operator manages an external job, store the external job ID using `task_instance.xcom_push(key='job_id', value=job_id)` so it's visible in the XCom tab.

---

**Q10: What is `conn_type` in a hook and why does it matter?**

`conn_type` is a string that categorizes the connection in Airflow's connection form. Setting it to a unique string (e.g., `"dataforge"`) means Airflow will show a customized connection form for your system when users create connections through the UI, displaying the right field labels (host, login, etc.) and hiding irrelevant fields. Without it, users see the generic connection form. To have a fully rendered custom form, you also need to implement `get_connection_form_widgets()` and `get_ui_field_behaviour()` class methods on the hook, and register the hook via `AirflowPlugin`.
