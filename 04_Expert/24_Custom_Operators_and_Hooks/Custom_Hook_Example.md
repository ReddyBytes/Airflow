# 24 — Custom Operators and Hooks: Custom Hook Example

## InternalAPIHook

A complete hook for a hypothetical internal REST API, with connection type registration, `get_conn()`, helper methods, and error handling.

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## The Internal API Being Wrapped

Hypothetical "DataForge" REST API:
```
Base URL:     https://dataforge.corp.com/api/v2
Auth:         Bearer token (in Connection.password)
              OR API key (in Connection.extra["api_key"])
Endpoints:
  POST /jobs               Submit a job → returns {job_id, status}
  GET  /jobs/{job_id}      Get job status → returns {job_id, status, result, error}
  DELETE /jobs/{job_id}    Cancel a running job
  GET  /datasets/{name}    Get dataset metadata → {name, status, row_count, updated_at}
  GET  /health             Health check → {status: "ok"}
```

---

## Connection Object Schema

```
Conn ID:    dataforge_default
Conn Type:  http  (or custom "dataforge" if plugin registered)
Host:       dataforge.corp.com
Schema:     https
Port:       443
Login:      svc_airflow           (used for audit logging)
Password:   Bearer token OR empty if using API key
Extra (JSON):
  {
    "api_key": "df_prod_abc123...",   (alternative auth)
    "timeout": 60,
    "verify_ssl": true,
    "api_version": "v2"
  }
```

---

## InternalAPIHook Implementation

```python
# hooks/dataforge_hook.py
"""
Hook for the DataForge internal REST API.

Connection setup (Airflow UI or environment variable):

    Conn ID:   dataforge_default
    Conn Type: HTTP
    Host:      dataforge.corp.com
    Schema:    https
    Port:      443
    Login:     svc_airflow
    Password:  df_token_abc123xyz      (Bearer token)
    Extra:     {"timeout": 60, "verify_ssl": true, "api_version": "v2"}

    OR via environment variable:
    AIRFLOW_CONN_DATAFORGE_DEFAULT='http://svc_airflow:df_token_abc123xyz@dataforge.corp.com:443/api/v2?api_version=v2'
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from airflow.exceptions import AirflowException, AirflowNotFoundException
from airflow.hooks.base import BaseHook

log = logging.getLogger(__name__)


class DataForgeAPIError(AirflowException):
    """Raised when DataForge returns a non-2xx response."""

    def __init__(self, status_code: int, endpoint: str, message: str):
        self.status_code = status_code
        self.endpoint = endpoint
        super().__init__(
            f"DataForge API error {status_code} on {endpoint}: {message}"
        )


class DataForgeJobNotFoundError(AirflowNotFoundException):
    """Raised when a job ID does not exist."""
    pass


class DataForgeHook(BaseHook):
    """
    Hook for the DataForge internal REST API.

    Features:
    - Reads credentials from Airflow Connection (never hardcoded)
    - Supports both Bearer token and API key authentication
    - Connection caching (one session per hook instance)
    - Automatic retry with exponential backoff for transient errors
    - Structured error handling with typed exceptions
    - SSL verification configurable per connection

    Basic usage:
        hook = DataForgeHook(conn_id="dataforge_default")
        job_id = hook.submit_job("daily_etl", {"date": "2026-03-15"})
        status = hook.get_job_status(job_id)
    """

    conn_name_attr = "dataforge_conn_id"
    default_conn_name = "dataforge_default"
    conn_type = "dataforge"
    hook_name = "DataForge"

    # HTTP status codes that warrant a retry
    RETRY_STATUS_CODES = {429, 502, 503, 504}

    def __init__(
        self,
        conn_id: str = default_conn_name,
        retry_count: int = 3,
        retry_backoff_factor: float = 1.0,
    ) -> None:
        super().__init__()
        self.dataforge_conn_id = conn_id
        self.retry_count = retry_count
        self.retry_backoff_factor = retry_backoff_factor
        self._session: requests.Session | None = None
        self._base_url: str | None = None

    # ──────────────────────────────────────────────────────────────────
    # Connection management
    # ──────────────────────────────────────────────────────────────────

    def get_conn(self) -> requests.Session:
        """
        Returns a pre-configured requests.Session with:
          - Authorization header (Bearer token or API key)
          - Default timeout from connection extra
          - Automatic retry for transient HTTP errors
          - SSL verification setting

        The session is cached — subsequent calls return the same session.
        """
        if self._session is not None:
            return self._session

        conn = self.get_connection(self.dataforge_conn_id)
        extra = conn.extra_dejson

        # Build base URL from connection components
        scheme = conn.schema or "https"
        host = conn.host
        port = conn.port
        api_version = extra.get("api_version", "v2")
        port_str = f":{port}" if port else ""
        self._base_url = f"{scheme}://{host}{port_str}/api/{api_version}"

        # Configure authentication
        session = requests.Session()
        if conn.password:
            session.headers["Authorization"] = f"Bearer {conn.password}"
            log.debug("DataForgeHook: using Bearer token auth for %s", host)
        elif extra.get("api_key"):
            session.headers["X-API-Key"] = extra["api_key"]
            log.debug("DataForgeHook: using API key auth for %s", host)
        else:
            raise AirflowException(
                f"Connection '{self.dataforge_conn_id}' has no password (Bearer token) "
                f"and no 'api_key' in extra. Cannot authenticate with DataForge."
            )

        session.headers["Content-Type"] = "application/json"
        session.headers["X-Airflow-Service"] = conn.login or "airflow"

        # Configure automatic retry for transient errors
        retry_strategy = Retry(
            total=self.retry_count,
            backoff_factor=self.retry_backoff_factor,
            status_forcelist=self.RETRY_STATUS_CODES,
            allowed_methods={"GET", "POST", "DELETE"},
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # SSL verification
        session.verify = extra.get("verify_ssl", True)
        if not session.verify:
            log.warning("DataForgeHook: SSL verification disabled for %s", host)

        # Default timeout (stored on session for use in _request)
        self._timeout = extra.get("timeout", 60)

        self._session = session
        return session

    def _url(self, path: str) -> str:
        """Build full URL from relative path."""
        if self._base_url is None:
            self.get_conn()  # triggers lazy init
        return urljoin(self._base_url + "/", path.lstrip("/"))

    def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Execute an HTTP request and handle errors uniformly.

        Args:
            method: HTTP method ("GET", "POST", "DELETE")
            path:   API path (relative to base URL)
            **kwargs: Passed directly to requests.Session.request()

        Returns:
            Parsed JSON response body

        Raises:
            DataForgeJobNotFoundError: On HTTP 404
            DataForgeAPIError:         On any other non-2xx response
            AirflowException:          On network-level failures
        """
        session = self.get_conn()
        url = self._url(path)
        kwargs.setdefault("timeout", self._timeout)

        log.debug("%s %s", method, url)
        try:
            response = session.request(method, url, **kwargs)
        except requests.exceptions.ConnectionError as e:
            raise AirflowException(f"Cannot connect to DataForge at {url}: {e}") from e
        except requests.exceptions.Timeout:
            raise AirflowException(f"DataForge request timed out: {method} {url}")

        if response.status_code == 404:
            raise DataForgeJobNotFoundError(
                f"DataForge resource not found: {method} {url}"
            )
        if not response.ok:
            try:
                error_body = response.json().get("message", response.text[:200])
            except Exception:
                error_body = response.text[:200]
            raise DataForgeAPIError(
                status_code=response.status_code,
                endpoint=f"{method} {path}",
                message=error_body,
            )

        if response.content:
            return response.json()
        return {}

    # ──────────────────────────────────────────────────────────────────
    # Job management methods
    # ──────────────────────────────────────────────────────────────────

    def submit_job(
        self,
        job_name: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Submit a job to DataForge.

        Args:
            job_name: Name of the job to run
            params:   Optional dict of job parameters

        Returns:
            job_id string

        Raises:
            AirflowException: If submission fails
        """
        payload = {"job_name": job_name, "params": params or {}}
        log.info("Submitting DataForge job: %s", job_name)
        response = self._request("POST", "/jobs", json=payload)
        job_id = response["job_id"]
        log.info("Job submitted: %s (id=%s)", job_name, job_id)
        return job_id

    def get_job_status(self, job_id: str) -> str:
        """
        Get the current status of a job.

        Returns one of: PENDING, RUNNING, SUCCESS, FAILED, CANCELLED, ERROR
        """
        response = self._request("GET", f"/jobs/{job_id}")
        return response["status"]

    def get_job_result(self, job_id: str) -> dict[str, Any]:
        """
        Get the result of a completed job.

        Returns the job result dict (contents depend on job type).

        Raises:
            AirflowException: If job is not in SUCCESS state
        """
        response = self._request("GET", f"/jobs/{job_id}")
        if response["status"] != "SUCCESS":
            raise AirflowException(
                f"Cannot get result for job {job_id}: status is {response['status']}"
            )
        return response.get("result", {})

    def get_job_error(self, job_id: str) -> str:
        """Get the error message from a failed job."""
        response = self._request("GET", f"/jobs/{job_id}")
        return response.get("error", "No error message available")

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Returns True if cancel was accepted, False if job already terminal.
        """
        try:
            self._request("DELETE", f"/jobs/{job_id}")
            log.info("Job %s cancellation requested", job_id)
            return True
        except DataForgeAPIError as e:
            if e.status_code == 409:  # Already in terminal state
                log.warning("Job %s is already in a terminal state, cannot cancel", job_id)
                return False
            raise

    # ──────────────────────────────────────────────────────────────────
    # Dataset methods
    # ──────────────────────────────────────────────────────────────────

    def get_dataset_status(self, dataset_name: str) -> str:
        """
        Get the status of a dataset.

        Returns one of: PENDING, PROCESSING, READY, ERROR
        """
        response = self._request("GET", f"/datasets/{dataset_name}")
        return response["status"]

    def get_dataset_metadata(self, dataset_name: str) -> dict[str, Any]:
        """Get full metadata for a dataset including row count and update time."""
        return self._request("GET", f"/datasets/{dataset_name}")

    # ──────────────────────────────────────────────────────────────────
    # Health check
    # ──────────────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """
        Test hook connectivity. Called by Airflow UI "Test Connection" button.
        """
        try:
            response = self._request("GET", "/health")
            if response.get("status") == "ok":
                return True, f"Connected to DataForge at {self._base_url}"
            return False, f"DataForge returned unexpected health response: {response}"
        except Exception as e:
            return False, str(e)
```

---

## Hook Registration as AirflowPlugin

Register the hook so it appears in the Airflow UI connection form:

```python
# plugins/dataforge_plugin.py
from airflow.plugins_manager import AirflowPlugin
from hooks.dataforge_hook import DataForgeHook


class DataForgePlugin(AirflowPlugin):
    name = "dataforge"
    hooks = [DataForgeHook]
```

---

## Hook Unit Tests

```python
# tests/test_dataforge_hook.py
from unittest.mock import MagicMock, patch, call

import pytest
import requests

from airflow.exceptions import AirflowException
from airflow.models import Connection

from hooks.dataforge_hook import DataForgeHook, DataForgeAPIError, DataForgeJobNotFoundError


@pytest.fixture
def mock_conn():
    return Connection(
        conn_id="dataforge_default",
        conn_type="http",
        host="dataforge.corp.com",
        schema="https",
        port=443,
        login="svc_airflow",
        password="test-bearer-token",
        extra='{"timeout": 30, "api_version": "v2"}',
    )


@pytest.fixture
def hook(mock_conn):
    with patch("hooks.dataforge_hook.BaseHook.get_connection", return_value=mock_conn):
        h = DataForgeHook()
        h.get_conn()  # initialize session
    return h


class TestDataForgeHookAuth:

    def test_bearer_token_in_header(self, mock_conn):
        with patch("hooks.dataforge_hook.BaseHook.get_connection", return_value=mock_conn):
            h = DataForgeHook()
            session = h.get_conn()
        assert session.headers["Authorization"] == "Bearer test-bearer-token"

    def test_api_key_auth_when_no_password(self):
        conn = Connection(
            conn_id="dataforge_default",
            conn_type="http",
            host="dataforge.corp.com",
            schema="https",
            extra='{"api_key": "df_key_123"}',
        )
        with patch("hooks.dataforge_hook.BaseHook.get_connection", return_value=conn):
            h = DataForgeHook()
            session = h.get_conn()
        assert session.headers["X-API-Key"] == "df_key_123"

    def test_raises_if_no_auth(self):
        conn = Connection(
            conn_id="dataforge_default",
            host="dataforge.corp.com",
            schema="https",
            extra="{}",
        )
        with patch("hooks.dataforge_hook.BaseHook.get_connection", return_value=conn):
            h = DataForgeHook()
            with pytest.raises(AirflowException, match="no password"):
                h.get_conn()


class TestDataForgeHookMethods:

    def test_submit_job_returns_job_id(self, hook):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.content = b'{"job_id": "abc-123", "status": "PENDING"}'
        mock_resp.json.return_value = {"job_id": "abc-123", "status": "PENDING"}
        hook._session.request = MagicMock(return_value=mock_resp)

        job_id = hook.submit_job("daily_etl", {"date": "2026-03-15"})
        assert job_id == "abc-123"

    def test_get_job_status_returns_status_string(self, hook):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.content = b'{"job_id": "abc-123", "status": "SUCCESS"}'
        mock_resp.json.return_value = {"job_id": "abc-123", "status": "SUCCESS"}
        hook._session.request = MagicMock(return_value=mock_resp)

        status = hook.get_job_status("abc-123")
        assert status == "SUCCESS"

    def test_404_raises_job_not_found(self, hook):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 404
        hook._session.request = MagicMock(return_value=mock_resp)

        with pytest.raises(DataForgeJobNotFoundError):
            hook.get_job_status("nonexistent-id")

    def test_500_raises_api_error_with_status_code(self, hook):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"message": "Internal server error"}
        hook._session.request = MagicMock(return_value=mock_resp)

        with pytest.raises(DataForgeAPIError) as exc_info:
            hook.submit_job("bad_job")
        assert exc_info.value.status_code == 500
```
