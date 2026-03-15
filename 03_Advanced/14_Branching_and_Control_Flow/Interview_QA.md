# 10 — Branching and Control Flow: Interview Q&A

---

**Q1. What is BranchPythonOperator and when would you use it?**

`BranchPythonOperator` calls a Python function that returns one or more task IDs. The scheduler runs only the returned task(s) and marks all other downstream tasks as SKIPPED. You use it when your pipeline has two or more genuine alternative paths — for example, routing to a production load vs. a staging load based on an environment variable, or sending a success notification vs. a failure notification.

---

**Q2. How does TriggerRule work?**

`TriggerRule` is a parameter on every Airflow task that controls when the task becomes eligible to run based on the states of its upstream (parent) tasks. The default is `ALL_SUCCESS` — the task only runs if every parent succeeded. Other rules like `ONE_FAILED`, `ALL_DONE`, and `NONE_FAILED` let you express richer conditions such as "run this cleanup task no matter what" or "run this alert as soon as any upstream task fails."

---

**Q3. What is the difference between ShortCircuitOperator and BranchPythonOperator?**

`ShortCircuitOperator` returns a boolean. If it returns `False`, all downstream tasks are skipped — there is no alternative path. It is a gate: the pipeline either continues or stops. `BranchPythonOperator` returns a task ID (or list of IDs) and actively routes the pipeline down a chosen path, while skipping the other paths. Use `ShortCircuitOperator` for a simple "should I proceed?" check, and `BranchPythonOperator` when you have two or more meaningful paths.

---

**Q4. What does ALL_DONE mean and when would you use it?**

`ALL_DONE` means the task runs as soon as all parents have finished, regardless of their outcome — whether they succeeded, failed, or were skipped. It is ideal for cleanup tasks (removing temp files, releasing locks, sending a final audit log) that must run no matter what happened upstream.

---

**Q5. Why does a join task after a BranchPythonOperator often get skipped, and how do you fix it?**

The default trigger rule is `ALL_SUCCESS`. After a branch, one path runs and the other is skipped. The join task sees a skipped parent, which is not a success, so it also gets skipped. Fix it by setting `trigger_rule="none_failed"` on the join task. This rule says: "run as long as no parent failed — skipped parents are acceptable."

---

**Q6. How do you implement a conditional notification that fires only when a task fails?**

Use `trigger_rule="one_failed"` on the notification task:

```python
alert = EmailOperator(
    task_id="send_alert",
    trigger_rule="one_failed",
    to="ops@example.com",
    subject="Pipeline failed",
    html_content="A task failed.",
)
[extract, transform, load] >> alert
```

`alert` runs as soon as any one of the three upstream tasks fails.

---

**Q7. Can BranchPythonOperator return more than one task ID?**

Yes. Return a list of task IDs and Airflow will run all of them, skipping everything else:

```python
def decide():
    return ["notify_slack", "update_dashboard"]
```

---

**Q8. What happens to a task that is SKIPPED vs FAILED?**

A SKIPPED task was intentionally bypassed by a branch or short-circuit — it is not an error. The DAG run can still succeed. A FAILED task encountered an exception or returned a failure signal. By default, downstream tasks of a failed task are not run (they stay in the `upstream_failed` state). The DAG run is marked as failed.

---

**Q9. What is NONE_FAILED and how is it different from ALL_SUCCESS?**

`NONE_FAILED` means: run this task if no parent has the FAILED state — parents can be SUCCESS or SKIPPED. `ALL_SUCCESS` requires every parent to be SUCCESS; a single SKIPPED parent will cause the task to be skipped too. After a branch where one path is always skipped, use `NONE_FAILED` for the join task.

---

**Q10. How would you build a data quality gate that stops the pipeline if quality is too low?**

Use `ShortCircuitOperator`:

```python
def quality_ok(ti, **context):
    score = ti.xcom_pull(task_ids="run_quality_checks", key="score")
    return score >= 0.95  # False short-circuits all downstream tasks

gate = ShortCircuitOperator(
    task_id="quality_gate",
    python_callable=quality_ok,
)

run_quality_checks >> gate >> load_to_production >> generate_report
```

If `quality_ok` returns `False`, `load_to_production` and `generate_report` are skipped and the DAG run finishes in a non-failed state (tasks are SKIPPED, not FAILED).
