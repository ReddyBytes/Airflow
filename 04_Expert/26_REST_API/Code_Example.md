# 26 — REST API: Code Examples

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: Python Script to Trigger DAG and Poll for Result

```python
#!/usr/bin/env python3
"""
trigger_dag.py — Trigger an Airflow DAG via REST API and wait for completion.

Usage:
    python trigger_dag.py --dag-id my_dag --conf '{"date": "2026-03-15"}'

Requirements:
    pip install requests
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any

import requests


class AirflowAPIClient:
    """Lightweight Airflow REST API client."""

    def __init__(self, base_url: str, token: str | None = None, username: str = "admin", password: str = "admin"):
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._username = username
        self._password = password

    def _get_token(self) -> str:
        """Fetch a JWT token using username/password."""
        response = requests.post(
            f"{self.base_url}/auth/token",
            json={"username": self._username, "password": self._password},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    @property
    def headers(self) -> dict[str, str]:
        if self._token is None:
            self._token = self._get_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def get(self, path: str, **params) -> dict:
        response = requests.get(
            f"{self.base_url}/api/v1{path}",
            headers=self.headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def post(self, path: str, body: dict) -> dict:
        response = requests.post(
            f"{self.base_url}/api/v1{path}",
            headers=self.headers,
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


def trigger_dag(
    client: AirflowAPIClient,
    dag_id: str,
    conf: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> str:
    """
    Trigger a DAG run and return the run_id.

    Args:
        client:  Initialized AirflowAPIClient
        dag_id:  DAG to trigger
        conf:    Optional conf dict passed to DAG run
        run_id:  Optional custom run ID (auto-generated if None)

    Returns:
        dag_run_id string
    """
    body: dict[str, Any] = {}
    if conf:
        body["conf"] = conf
    if run_id:
        body["dag_run_id"] = run_id

    print(f"Triggering DAG '{dag_id}' with conf: {conf}")
    response = client.post(f"/dags/{dag_id}/dagRuns", body)
    run_id = response["dag_run_id"]
    print(f"Run triggered: {run_id}")
    return run_id


def poll_dag_run(
    client: AirflowAPIClient,
    dag_id: str,
    run_id: str,
    timeout: int = 3600,
    poll_interval: int = 30,
) -> str:
    """
    Poll a DAG run until it reaches a terminal state.

    Args:
        client:        Initialized AirflowAPIClient
        dag_id:        DAG ID
        run_id:        DAG run ID to poll
        timeout:       Maximum seconds to wait
        poll_interval: Seconds between polls

    Returns:
        Final state string ('success', 'failed', etc.)

    Raises:
        TimeoutError: If timeout exceeded before terminal state
    """
    deadline = time.monotonic() + timeout
    terminal_states = {"success", "failed", "upstream_failed"}

    while time.monotonic() < deadline:
        response = client.get(f"/dags/{dag_id}/dagRuns/{run_id}")
        state = response["state"]
        elapsed = int(timeout - (deadline - time.monotonic()))
        print(f"  [{elapsed:4d}s] State: {state}")

        if state in terminal_states:
            return state

        time.sleep(poll_interval)

    raise TimeoutError(
        f"DAG '{dag_id}' run '{run_id}' did not complete within {timeout}s"
    )


def get_failed_tasks(
    client: AirflowAPIClient,
    dag_id: str,
    run_id: str,
) -> list[dict]:
    """Return list of failed task instances for a DAG run."""
    response = client.get(f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances")
    return [
        ti for ti in response.get("task_instances", [])
        if ti["state"] in ("failed", "upstream_failed")
    ]


def main():
    parser = argparse.ArgumentParser(description="Trigger Airflow DAG and wait for completion")
    parser.add_argument("--base-url", default="http://localhost:8080", help="Airflow base URL")
    parser.add_argument("--dag-id", required=True, help="DAG ID to trigger")
    parser.add_argument("--conf", default="{}", help="JSON conf dict")
    parser.add_argument("--run-id", default=None, help="Custom run ID")
    parser.add_argument("--timeout", type=int, default=3600, help="Max wait time in seconds")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between polls")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()

    client = AirflowAPIClient(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
    )

    try:
        conf = json.loads(args.conf)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid --conf JSON: {e}")
        sys.exit(1)

    # 1. Trigger
    run_id = trigger_dag(client, args.dag_id, conf=conf, run_id=args.run_id)

    # 2. Poll
    print(f"\nPolling every {args.poll_interval}s (max {args.timeout}s)...")
    final_state = poll_dag_run(
        client, args.dag_id, run_id,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )

    # 3. Report
    if final_state == "success":
        print(f"\nSUCCESS: DAG '{args.dag_id}' run '{run_id}' completed successfully.")
        sys.exit(0)
    else:
        print(f"\nFAILED: DAG '{args.dag_id}' run '{run_id}' finished with state '{final_state}'")
        failed_tasks = get_failed_tasks(client, args.dag_id, run_id)
        if failed_tasks:
            print("Failed tasks:")
            for ti in failed_tasks:
                print(f"  - {ti['task_id']} (try {ti['try_number']}): {ti['state']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## Example 2: CI/CD Integration Script

A shell script suitable for embedding in GitHub Actions, GitLab CI, or Jenkins pipelines.

```bash
#!/bin/bash
# ci_airflow_deploy.sh
#
# Usage in CI/CD pipeline (after deployment):
#   export AIRFLOW_URL="http://airflow.corp.com:8080"
#   export AIRFLOW_USER="ci_service_account"
#   export AIRFLOW_PASS="$CI_AIRFLOW_TOKEN"
#   ./ci_airflow_deploy.sh rebuild_warehouse '{"version": "v1.2.3", "env": "prod"}'
#
# Exit codes:
#   0 = DAG completed successfully
#   1 = DAG failed or script error
#   2 = Timeout exceeded

set -euo pipefail

DAG_ID="${1:?Usage: $0 <dag_id> [conf_json]}"
CONF="${2:-{}}"
AIRFLOW_URL="${AIRFLOW_URL:-http://localhost:8080}"
AIRFLOW_USER="${AIRFLOW_USER:-admin}"
AIRFLOW_PASS="${AIRFLOW_PASS:-admin}"
MAX_WAIT="${MAX_WAIT_SECONDS:-1800}"   # 30 minutes
POLL_INTERVAL="${POLL_INTERVAL:-30}"

# ── Authentication ───────────────────────────────────────────────────────────

echo "[CI] Authenticating with Airflow at $AIRFLOW_URL..."
TOKEN_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$AIRFLOW_URL/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$AIRFLOW_USER\", \"password\": \"$AIRFLOW_PASS\"}")

HTTP_CODE=$(echo "$TOKEN_RESPONSE" | tail -1)
TOKEN_JSON=$(echo "$TOKEN_RESPONSE" | head -1)

if [ "$HTTP_CODE" != "200" ]; then
  echo "[CI] ERROR: Authentication failed (HTTP $HTTP_CODE)"
  echo "$TOKEN_JSON" | python3 -m json.tool 2>/dev/null || echo "$TOKEN_JSON"
  exit 1
fi

TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
AUTH_HEADER="Authorization: Bearer $TOKEN"

echo "[CI] Authenticated successfully."

# ── Pre-check: Is DAG paused? ────────────────────────────────────────────────

IS_PAUSED=$(curl -s -H "$AUTH_HEADER" "$AIRFLOW_URL/api/v1/dags/$DAG_ID" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('is_paused', True))")

if [ "$IS_PAUSED" = "True" ]; then
  echo "[CI] DAG '$DAG_ID' is paused. Unpausing..."
  curl -s -X PATCH -H "$AUTH_HEADER" -H "Content-Type: application/json" \
    -d '{"is_paused": false}' "$AIRFLOW_URL/api/v1/dags/$DAG_ID" > /dev/null
fi

# ── Trigger ───────────────────────────────────────────────────────────────────

CI_RUN_ID="ci_$(date +%Y%m%dT%H%M%S)_${CI_PIPELINE_ID:-local}"
echo "[CI] Triggering DAG '$DAG_ID' (run_id: $CI_RUN_ID)..."
echo "[CI] conf: $CONF"

TRIGGER_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$AIRFLOW_URL/api/v1/dags/$DAG_ID/dagRuns" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d "{\"dag_run_id\": \"$CI_RUN_ID\", \"conf\": $CONF}")

HTTP_CODE=$(echo "$TRIGGER_RESPONSE" | tail -1)
TRIGGER_JSON=$(echo "$TRIGGER_RESPONSE" | head -1)

if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "201" ]; then
  echo "[CI] ERROR: Trigger failed (HTTP $HTTP_CODE)"
  echo "$TRIGGER_JSON"
  exit 1
fi

RUN_ID=$(echo "$TRIGGER_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['dag_run_id'])")
echo "[CI] Run triggered: $RUN_ID"
echo "[CI] UI: $AIRFLOW_URL/dags/$DAG_ID/grid"

# ── Poll ──────────────────────────────────────────────────────────────────────

echo "[CI] Polling for completion (max ${MAX_WAIT}s, interval ${POLL_INTERVAL}s)..."
ELAPSED=0
FINAL_STATE=""

while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
  sleep "$POLL_INTERVAL"
  ELAPSED=$((ELAPSED + POLL_INTERVAL))

  STATE=$(curl -s -H "$AUTH_HEADER" \
    "$AIRFLOW_URL/api/v1/dags/$DAG_ID/dagRuns/$RUN_ID" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")

  echo "[CI] [${ELAPSED}s / ${MAX_WAIT}s] State: $STATE"

  case "$STATE" in
    success)
      FINAL_STATE="success"
      break
      ;;
    failed|upstream_failed)
      FINAL_STATE="$STATE"
      break
      ;;
    running|queued)
      # continue polling
      ;;
    *)
      echo "[CI] ERROR: Unexpected state '$STATE'"
      exit 1
      ;;
  esac
done

# ── Result ────────────────────────────────────────────────────────────────────

if [ -z "$FINAL_STATE" ]; then
  echo "[CI] TIMEOUT: DAG did not complete within ${MAX_WAIT}s"
  exit 2
fi

if [ "$FINAL_STATE" = "success" ]; then
  echo "[CI] SUCCESS: DAG '$DAG_ID' completed."
  exit 0
else
  echo "[CI] FAILED: DAG '$DAG_ID' finished with state '$FINAL_STATE'"

  # Print failed tasks
  echo "[CI] Failed tasks:"
  curl -s -H "$AUTH_HEADER" \
    "$AIRFLOW_URL/api/v1/dags/$DAG_ID/dagRuns/$RUN_ID/taskInstances" \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for ti in data.get('task_instances', []):
    if ti['state'] in ('failed', 'upstream_failed'):
        print(f\"  - {ti['task_id']} (try {ti['try_number']}): {ti['state']}\")
"
  exit 1
fi
```

---

## Example 3: Airflow API Client Wrapper Class

A reusable, well-structured Python client suitable for use in internal tooling and automation scripts.

```python
# airflow_client/client.py
"""
Production-grade Airflow REST API client.

Features:
- JWT authentication with automatic refresh
- Retry on transient errors (429, 502, 503)
- Type-annotated response models
- Pagination helpers
- Context manager support

Usage:
    from airflow_client import AirflowClient

    with AirflowClient("http://airflow.corp.com:8080", "admin", "admin") as client:
        run = client.trigger_dag("my_dag", conf={"date": "2026-03-15"})
        client.wait_for_run(run["dag_run_id"], "my_dag")
"""
from __future__ import annotations

import time
from typing import Any, Generator, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class AirflowAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


class AirflowClient:
    """
    Thread-safe Airflow REST API client with JWT auth and retry logic.
    """

    TERMINAL_STATES = {"success", "failed", "upstream_failed"}

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._token: str | None = None

        # Session with automatic retry
        self._session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=1.0,
            status_forcelist={429, 502, 503, 504},
        )
        self._session.mount("http://", HTTPAdapter(max_retries=retry))
        self._session.mount("https://", HTTPAdapter(max_retries=retry))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._session.close()

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _authenticate(self) -> None:
        """Fetch and cache a JWT token."""
        response = self._session.post(
            f"{self.base_url}/auth/token",
            json={"username": self._username, "password": self._password},
            timeout=self._timeout,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]

    @property
    def _headers(self) -> dict[str, str]:
        if self._token is None:
            self._authenticate()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ── HTTP primitives ───────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> dict | None:
        kwargs.setdefault("timeout", self._timeout)
        response = self._session.request(
            method,
            f"{self.base_url}/api/v1{path}",
            headers=self._headers,
            **kwargs,
        )
        if response.status_code == 401:
            # Token expired — refresh and retry once
            self._token = None
            self._authenticate()
            response = self._session.request(
                method,
                f"{self.base_url}/api/v1{path}",
                headers=self._headers,
                **kwargs,
            )

        if not response.ok:
            try:
                msg = response.json().get("detail", response.text[:200])
            except Exception:
                msg = response.text[:200]
            raise AirflowAPIError(response.status_code, msg)

        if response.content:
            return response.json()
        return None

    # ── Pagination ────────────────────────────────────────────────────────────

    def paginate(self, path: str, key: str, page_size: int = 100, **filters) -> Iterator[dict]:
        """Generator that yields all items across all pages."""
        offset = 0
        while True:
            response = self._request("GET", path, params={**filters, "limit": page_size, "offset": offset})
            items = response.get(key, [])
            yield from items
            if len(items) < page_size:
                break
            offset += page_size

    # ── DAGs ─────────────────────────────────────────────────────────────────

    def list_dags(self, only_active: bool = True, tags: list[str] | None = None) -> list[dict]:
        params = {"only_active": only_active}
        if tags:
            params["tags"] = tags
        return list(self.paginate("/dags", "dags", **params))

    def get_dag(self, dag_id: str) -> dict:
        return self._request("GET", f"/dags/{dag_id}")

    def pause_dag(self, dag_id: str) -> dict:
        return self._request("PATCH", f"/dags/{dag_id}", json={"is_paused": True})

    def unpause_dag(self, dag_id: str) -> dict:
        return self._request("PATCH", f"/dags/{dag_id}", json={"is_paused": False})

    # ── DAG Runs ──────────────────────────────────────────────────────────────

    def trigger_dag(
        self,
        dag_id: str,
        conf: dict[str, Any] | None = None,
        dag_run_id: str | None = None,
        logical_date: str | None = None,
    ) -> dict:
        """Trigger a DAG run and return the run dict."""
        body: dict[str, Any] = {}
        if conf:
            body["conf"] = conf
        if dag_run_id:
            body["dag_run_id"] = dag_run_id
        if logical_date:
            body["logical_date"] = logical_date
        return self._request("POST", f"/dags/{dag_id}/dagRuns", json=body)

    def get_dag_run(self, dag_id: str, run_id: str) -> dict:
        return self._request("GET", f"/dags/{dag_id}/dagRuns/{run_id}")

    def list_dag_runs(
        self,
        dag_id: str,
        state: str | None = None,
        limit: int = 25,
    ) -> list[dict]:
        params = {"limit": limit, "order_by": "-execution_date"}
        if state:
            params["state"] = state
        return self._request("GET", f"/dags/{dag_id}/dagRuns", params=params).get("dag_runs", [])

    def wait_for_run(
        self,
        dag_id: str,
        run_id: str,
        timeout: int = 3600,
        poll_interval: int = 30,
        verbose: bool = True,
    ) -> str:
        """
        Block until the DAG run reaches a terminal state.

        Returns:
            Final state string

        Raises:
            TimeoutError: If run doesn't complete within timeout seconds
            RuntimeError: If run ends in a failure state
        """
        deadline = time.monotonic() + timeout
        last_state = None

        while time.monotonic() < deadline:
            run = self.get_dag_run(dag_id, run_id)
            state = run["state"]

            if state != last_state and verbose:
                elapsed = int(timeout - (deadline - time.monotonic()))
                print(f"  [{elapsed:4d}s] {dag_id}/{run_id}: {state}")
                last_state = state

            if state in self.TERMINAL_STATES:
                if state != "success":
                    raise RuntimeError(
                        f"DAG '{dag_id}' run '{run_id}' ended with state '{state}'"
                    )
                return state

            time.sleep(poll_interval)

        raise TimeoutError(
            f"DAG '{dag_id}' run '{run_id}' did not complete within {timeout}s"
        )

    # ── Variables ─────────────────────────────────────────────────────────────

    def get_variable(self, key: str) -> str:
        return self._request("GET", f"/variables/{key}")["value"]

    def set_variable(self, key: str, value: str, description: str = "") -> dict:
        try:
            return self._request("PATCH", f"/variables/{key}", json={"key": key, "value": value})
        except AirflowAPIError as e:
            if e.status_code == 404:
                return self._request("POST", "/variables", json={"key": key, "value": value, "description": description})
            raise

    # ── Health ────────────────────────────────────────────────────────────────

    def is_healthy(self) -> bool:
        try:
            response = self._request("GET", "/health")
            return (
                response.get("metadatabase", {}).get("status") == "healthy"
                and response.get("scheduler", {}).get("status") == "healthy"
            )
        except Exception:
            return False
```

### Usage Examples

```python
# Trigger and wait
from airflow_client.client import AirflowClient

with AirflowClient("http://airflow.corp.com:8080", "svc_ci", "ci_token") as client:
    # Trigger
    run = client.trigger_dag(
        "rebuild_warehouse",
        conf={"version": "v1.2.3"},
        dag_run_id=f"ci_v1.2.3_{int(time.time())}",
    )
    print(f"Triggered: {run['dag_run_id']}")

    # Wait (raises RuntimeError on failure)
    client.wait_for_run("rebuild_warehouse", run["dag_run_id"], timeout=1800)
    print("Pipeline completed successfully!")

# List all failed runs for investigation
with AirflowClient("http://airflow.corp.com:8080", "admin", "admin") as client:
    failed_runs = client.list_dag_runs("my_dag", state="failed")
    for run in failed_runs:
        print(f"{run['dag_run_id']}: {run['state']} @ {run['execution_date']}")
```
