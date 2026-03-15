# 09 — XComs: Interview Q&A

---

**Q1. What is an XCom in Airflow?**

XCom (cross-communication) is Airflow's built-in mechanism for passing small pieces of data between tasks within the same DAG run. Values are stored in the metadata database's `xcom` table, keyed by `dag_id`, `run_id`, `task_id`, and a user-defined `key`. Tasks can push values and any downstream task can pull them.

---

**Q2. How do you push an XCom value from a task?**

Two ways:
1. **Explicit push** — call `ti.xcom_push(key="my_key", value=my_value)` inside the task callable.
2. **Return value** — simply return a value from the callable. Airflow automatically pushes it under the key `"return_value"`.

---

**Q3. How do you pull an XCom value in a downstream task?**

Call `ti.xcom_pull(task_ids="upstream_task_id", key="my_key")` inside the task callable. If the upstream task used a return value (key `"return_value"`), you can omit the `key` argument.

---

**Q4. What is the TaskFlow API and how does it simplify XComs?**

The TaskFlow API (introduced in Airflow 2.0) uses the `@task` decorator to turn Python functions into tasks. When you pass the return value of one `@task` function as an argument to another, Airflow automatically wires the XCom push and pull. You write plain Python — no `ti.xcom_push`, no `ti.xcom_pull`, no `**context` boilerplate.

---

**Q5. What are the size limits for XComs?**

Airflow does not enforce a hard size limit by default, but XComs are stored in the metadata database and are intended for small metadata — filenames, IDs, counts, status codes, or small dicts. Anything larger than a few kilobytes should be written to external storage (S3, GCS, a database) and only the path or identifier passed as an XCom.

---

**Q6. When should you NOT use XComs?**

- When passing a Pandas DataFrame, numpy array, or any large data structure.
- When the value exceeds ~1 MB.
- When you need to query, filter, or join the data downstream (put it in a database instead).
- When the data needs to outlive the DAG run (put it in persistent storage).

---

**Q7. How are XComs scoped to a DAG run?**

Each XCom record includes the `run_id` field. When a DAG runs twice concurrently, each run writes and reads its own XComs. A task pulling an XCom only sees values pushed in the same run by default — you must explicitly specify a different `run_id` to cross-run boundaries.

---

**Q8. What is the difference between the old-style (provide_context) and the new TaskFlow API style?**

In Airflow 1.x, you had to set `provide_context=True` on `PythonOperator` and add `**context` to the callable to get access to `ti` for XCom operations. In Airflow 2.0+ with `@task`, context injection is automatic and XComs are handled by simply returning and receiving values, making the code significantly cleaner.

---

**Q9. How do you clear XComs for a specific task run?**

- **From the UI**: Navigate to Browse → XComs, filter by DAG and task, and delete records.
- **Automatically**: XComs are cleared when you clear the task instance from the DAG run view.
- **Via cleanup task**: You can add a final task that queries and deletes XCom records using the Airflow ORM (`session.query(XCom).filter(...).delete()`).

---

**Q10. Can you pull an XCom from a different DAG?**

Yes. Pass `dag_id` explicitly to `xcom_pull`:

```python
value = ti.xcom_pull(dag_id="other_dag_id", task_ids="some_task", key="my_key")
```

This is generally discouraged as it creates hidden coupling between DAGs. A better design is to share data through an external database or storage layer rather than reaching into another DAG's XCom store.
