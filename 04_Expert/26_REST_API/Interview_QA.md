# 26 — REST API: Interview Q&A

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

**Q1: What is the Airflow REST API and when would you use it?**

The Airflow REST API is an HTTP/JSON interface to Airflow's core operations: triggering DAG runs, checking run status, managing variables and connections, clearing task instances, managing pools, and health checks. Use it when external systems need to interact with Airflow programmatically — CI/CD pipelines that trigger DAGs after deployment, monitoring systems that check DAG health, data quality frameworks that verify pipeline completion, or orchestration systems that coordinate multiple Airflow deployments. In Airflow 3, the API is served by a dedicated API Server process, separate from the web UI.

---

**Q2: How do you authenticate with the Airflow REST API?**

In Airflow 3, the recommended method is JWT Bearer tokens. First, POST to `/auth/token` with username/password credentials to receive a short-lived JWT access token. Include the token in subsequent requests as `Authorization: Bearer <token>`. Tokens expire after a configurable period (`access_token_lifetime_minutes` in `airflow.cfg`). For CI/CD systems, use a dedicated service account with minimal permissions. Basic authentication (`-u user:pass`) is also supported but should be disabled in production environments. API key authentication can be configured through custom auth managers.

---

**Q3: How do you trigger a DAG via the REST API and pass parameters to it?**

POST to `/api/v1/dags/{dag_id}/dagRuns` with a JSON body containing `conf`:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"conf": {"env": "production", "date": "2026-03-15"}, "dag_run_id": "ci_deploy_v1"}' \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns"
```
In the DAG, access `conf` via `{{ dag_run.conf.env }}` in templates or `context['dag_run'].conf['env']` in Python. You can also specify `logical_date` to trigger for a specific execution date, or leave it out for an immediate run with the current timestamp.

---

**Q4: How do you poll for DAG run completion after triggering via API?**

After triggering, store the `dag_run_id` from the response. Periodically GET `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}` and check the `state` field. Terminal states are `success` and `failed` (and `upstream_failed`). Non-terminal states are `running` and `queued`. A robust implementation: poll every 30–60 seconds, respect a maximum timeout (e.g., 30 minutes), and treat any state other than `success` as a failure. Always set a timeout — a DAG that hangs indefinitely should fail the CI pipeline, not hang it.

---

**Q5: What changed in the Airflow REST API between v2 and v3?**

The major structural change is that the API is now served by a dedicated **API Server** process rather than the Web Server, enabling independent scaling. Authentication moved to pluggable Auth Managers, with JWT as the primary method. The `execution_date` field was renamed to `logical_date` throughout, reflecting the semantic clarification from Airflow 2.2+. The API Server can be deployed separately from the UI, allowing API access without exposing the web interface. The base path `/api/v1/` remains unchanged for backward compatibility with existing clients.

---

**Q6: How does pagination work in the REST API?**

All list endpoints (`/dags`, `/dagRuns`, `/taskInstances`, etc.) support `limit` and `offset` query parameters. `limit` controls how many items to return per call (default 100, max 100). `offset` skips the first N items for page traversal. The response always includes `total_entries` — the total count — so you can calculate total pages: `pages = ceil(total_entries / limit)`. Use `order_by` to control sort order, prefixed with `-` for descending: `order_by=-execution_date` gives newest runs first.

---

**Q7: How do you build a Python client that triggers a DAG and waits for success?**

```python
import time
import requests

def trigger_and_wait(base_url, dag_id, conf, token, timeout=1800, poll_interval=30):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Trigger
    resp = requests.post(f"{base_url}/api/v1/dags/{dag_id}/dagRuns",
                        headers=headers, json={"conf": conf})
    resp.raise_for_status()
    run_id = resp.json()["dag_run_id"]

    # Poll
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{base_url}/api/v1/dags/{dag_id}/dagRuns/{run_id}", headers=headers)
        state = resp.json()["state"]
        if state == "success":
            return True
        if state in ("failed", "upstream_failed"):
            raise Exception(f"DAG {dag_id} run {run_id} failed with state={state}")
        time.sleep(poll_interval)
    raise TimeoutError(f"DAG {dag_id} did not complete within {timeout}s")
```

---

**Q8: How do you use the API to manage connections — for example, during a blue/green deployment?**

During blue/green deployments where the database endpoint changes:
1. POST `/api/v1/connections` to create a new connection with the new endpoint, or
2. PATCH `/api/v1/connections/{connection_id}` to update the existing connection's `host` and `password` fields.

```bash
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"host": "new-db.prod.corp.com", "password": "new_password"}' \
  "http://localhost:8080/api/v1/connections/postgres_prod"
```

Note: In environments using a secrets backend (Vault, AWS Secrets Manager), do NOT use the API to manage connections — update them in the secrets backend directly. The API only manages the metadata DB layer.

---

**Q9: How do you clear failed task instances via the API?**

Use POST `/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/clear`:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "dry_run": false,
    "task_ids": ["failed_task"],
    "include_downstream": true,
    "reset_dag_runs": true
  }' \
  "http://localhost:8080/api/v1/dags/my_dag/dagRuns/run_id/taskInstances/clear"
```
Always do a `"dry_run": true` call first to see which tasks would be cleared. `include_downstream: true` clears all tasks that depend on the cleared task. `reset_dag_runs: true` resets the DAG run state from failed back to running.

---

**Q10: What is the difference between deleting a DAG run and clearing a DAG run?**

**Clearing** a DAG run resets task instances in that run to `None` state, allowing them to be re-executed. The DAG run itself continues to exist and will transition back to `running`. This is the standard way to retry a failed pipeline — clear the failed tasks, they run again from scratch. **Deleting** a DAG run (`DELETE /api/v1/dags/{dag_id}/dagRuns/{dag_run_id}`) permanently removes the run and all its task instance records from the metadata database. This is irreversible and removes all log references and XCom data. Use delete for cleanup of test/erroneous runs, never for production retries.
