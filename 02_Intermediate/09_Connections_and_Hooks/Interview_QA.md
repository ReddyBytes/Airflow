# 07 — Connections and Hooks: Interview Q&A

---

**Q1. What is an Airflow Connection and why would you use one?**

A Connection is a named credential record stored in Airflow's metadata database (or a secrets backend). It holds the host, port, login, password, and extra configuration needed to reach an external system. You use Connections so that your DAG code never contains raw credentials — the DAG just references a `conn_id` string, and Airflow resolves the actual credentials at runtime.

---

**Q2. What is a Hook in Airflow?**

A Hook is a Python class that reads a Connection by `conn_id` and uses those credentials to open a session with an external system. It exposes helper methods for common operations — for example, `PostgresHook.get_records(sql)` runs a query and returns rows. Hooks live in provider packages and extend `BaseHook`.

---

**Q3. What is the difference between a Hook and an Operator?**

An Operator is a high-level task definition — it uses a Hook internally to do the actual work. A Hook is the low-level connection layer you call directly when you need custom logic inside a `PythonOperator`. Think of Operators as batteries-included wrappers around Hooks.

---

**Q4. How do you store Airflow Connections securely in production?**

Use a **secrets backend** such as AWS Secrets Manager, HashiCorp Vault, or GCP Secret Manager. Configure the backend in `airflow.cfg` under `[secrets]`. Airflow will look up connections there first, so credentials are never stored in the metadata database. Avoid using the UI for production secrets.

---

**Q5. What are the three ways to add a Connection in Airflow?**

1. **Airflow UI** — Admin → Connections → add a record. Good for local dev.
2. **Environment variable** — `AIRFLOW_CONN_<CONN_ID_UPPER>=<URI>`. Good for containers and CI/CD.
3. **Secrets backend** — Vault, AWS Secrets Manager, etc. Required for production.

---

**Q6. What is the environment variable format for a Connection?**

```
AIRFLOW_CONN_<CONN_ID_IN_UPPERCASE>=<conn_type>://<login>:<password>@<host>:<port>/<schema>
```

Example:
```
AIRFLOW_CONN_MY_POSTGRES=postgresql://user:pass@db-host:5432/mydb
```
Special characters in login or password must be URL-encoded.

---

**Q7. What is a Connection URI and what does it look like?**

A Connection URI encodes all connection fields in a single string following the format:
```
<scheme>://<login>:<password>@<host>:<port>/<schema>?<extra_key>=<extra_value>
```
Airflow uses this format for environment variables and the CLI. The `scheme` maps to `conn_type` (e.g., `postgresql`, `http`, `aws`).

---

**Q8. How would you test that a Connection is working?**

Several approaches:
- In the Airflow UI, open the connection record and click **Test** (available for many types).
- Write a small `PythonOperator` that instantiates the Hook and makes a simple call (e.g., `hook.get_records("SELECT 1")`).
- Use the CLI: `airflow connections get <conn_id>` to verify the record exists.

---

**Q9. Can you use a Hook outside of a task function?**

Technically yes, but you should not call a Hook at DAG parse time (module level). Hooks make live connections and may fail during parsing if the external system is unreachable or if the metadata DB is unavailable. Always instantiate Hooks inside the callable passed to an Operator, or inside a `@task` function.

---

**Q10. What does `BaseHook.get_connection(conn_id)` return?**

It returns a `Connection` object with attributes: `conn_id`, `conn_type`, `host`, `schema`, `login`, `password`, `port`, and `extra`. You can call it from any Hook or custom code to inspect connection details without going through a specific Hook class.
