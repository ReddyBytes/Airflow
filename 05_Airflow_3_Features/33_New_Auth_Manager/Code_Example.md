# New Auth Manager — Code Examples

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Edge Executor](../34_Edge_Executor/Theory.md)**

---

## Example 1: Configuring SimpleAuthManager (Development)

SimpleAuthManager is the fastest way to get Airflow running locally without setting up FAB's database tables.

```ini
# airflow.cfg
[core]
auth_manager = airflow.auth.managers.simple.SimpleAuthManager

[simple_auth_manager]
# Format: username:password:role  (comma-separated for multiple users)
# Roles: admin, op, user, viewer
users = admin:admin:admin,dev:devpass:op,demo:demo:viewer
```

Using environment variables (preferred for Docker):

```yaml
# docker-compose.yml
x-airflow-common:
  &airflow-common
  image: apache/airflow:3.0.0
  environment:
    AIRFLOW__CORE__AUTH_MANAGER: airflow.auth.managers.simple.SimpleAuthManager
    AIRFLOW__SIMPLE_AUTH_MANAGER__USERS: "admin:admin123:admin,viewer:view456:viewer"
    AIRFLOW__SIMPLE_AUTH_MANAGER__PASSWORDS_FILE: ""  # disable file-based passwords
```

> **Warning:** SimpleAuthManager stores passwords in plain text. Use only for local development.

---

## Example 2: Configuring FabAuthManager (Production)

FabAuthManager requires the FAB provider package and uses a proper user database.

```bash
pip install apache-airflow-providers-fab
```

```ini
# airflow.cfg
[core]
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager

[fab]
# Automatically create admin user on first startup (dev convenience — disable in prod)
auth_backend = airflow.providers.fab.auth.backend.basic_auth
```

```yaml
# docker-compose.yml — production-style setup with FabAuthManager
x-airflow-common:
  &airflow-common
  image: apache/airflow:3.0.0
  environment:
    AIRFLOW__CORE__AUTH_MANAGER: airflow.providers.fab.auth_manager.FabAuthManager
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    # Do NOT set _AIRFLOW_WWW_USER_CREATE in production — create users via CLI or UI

services:
  airflow-init:
    <<: *airflow-common
    command: >
      bash -c "
        airflow db migrate &&
        airflow users create
          --username admin
          --firstname Admin
          --lastname User
          --role Admin
          --email admin@example.com
          --password '$AIRFLOW_ADMIN_PASSWORD'
      "
    environment:
      <<: *airflow-common-env
      AIRFLOW_ADMIN_PASSWORD: ${AIRFLOW_ADMIN_PASSWORD:?err}
```

---

## Example 3: RBAC Setup — Creating Roles and Permissions

```bash
# ── Create custom roles ────────────────────────────────────────────────────────

# Role for data engineers: full DAG access + connections + variables
airflow roles create DataEngineer

airflow roles add-perms --role DataEngineer --resource "DAGs"         --action "can_read"
airflow roles add-perms --role DataEngineer --resource "DAGs"         --action "can_edit"
airflow roles add-perms --role DataEngineer --resource "DAG Runs"     --action "can_create"
airflow roles add-perms --role DataEngineer --resource "DAG Runs"     --action "can_read"
airflow roles add-perms --role DataEngineer --resource "Task Instances" --action "can_read"
airflow roles add-perms --role DataEngineer --resource "Connections"  --action "can_read"
airflow roles add-perms --role DataEngineer --resource "Variables"    --action "can_read"
airflow roles add-perms --role DataEngineer --resource "Variables"    --action "can_edit"

# Role for analysts: read-only DAGs + can trigger
airflow roles create Analyst

airflow roles add-perms --role Analyst --resource "DAGs"     --action "can_read"
airflow roles add-perms --role Analyst --resource "DAG Runs" --action "can_create"
airflow roles add-perms --role Analyst --resource "DAG Runs" --action "can_read"
airflow roles add-perms --role Analyst --resource "Task Instances" --action "can_read"

# ── Assign roles to users ──────────────────────────────────────────────────────

airflow users create \
  --username alice \
  --firstname Alice \
  --lastname Smith \
  --role DataEngineer \
  --email alice@example.com \
  --password changeme

airflow users create \
  --username bob \
  --firstname Bob \
  --lastname Jones \
  --role Analyst \
  --email bob@example.com \
  --password changeme
```

### DAG-level access control in code

```python
# dags/finance_pipeline.py
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

with DAG(
    dag_id="finance_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    # Only "FinanceTeam" and "Admin" roles can see/interact with this DAG
    access_control={
        "FinanceTeam": {"can_read", "can_edit", "can_delete"},
        "Admin":       {"can_read", "can_edit", "can_delete"},
        "Analyst":     {"can_read"},  # Analysts can see but not modify
    },
) as dag:

    @PythonOperator(task_id="run_finance_report", python_callable=lambda: None)
    def run_report():
        pass
```

---

## Example 4: OAuth2 Configuration (Google)

```python
# webserver_config.py  — place in $AIRFLOW_HOME/webserver_config.py
from flask_appbuilder.security.manager import AUTH_OAUTH

# Use OAuth2 for authentication
AUTH_TYPE = AUTH_OAUTH

OAUTH_PROVIDERS = [
    {
        "name": "google",
        "icon": "fa-google",
        "token_key": "access_token",
        "remote_app": {
            "client_id":     "123456789-abc.apps.googleusercontent.com",
            "client_secret": "GOCSPX-your-secret",
            "api_base_url":  "https://www.googleapis.com/oauth2/v2/",
            "client_kwargs": {"scope": "email profile"},
            "access_token_url":  "https://accounts.google.com/o/oauth2/token",
            "authorize_url":     "https://accounts.google.com/o/oauth2/auth",
            "jwks_uri":          "https://www.googleapis.com/oauth2/v3/certs",
            "request_token_url": None,
        },
    }
]

# Auto-register new users after their first OAuth login
AUTH_USER_REGISTRATION      = True
AUTH_USER_REGISTRATION_ROLE = "Viewer"  # Default role for new OAuth users

# Optional: require users to have an email from your domain
# AUTH_USER_REGISTRATION_ROLE_JMESPATH = "..."
```

Mount this file in Docker:

```yaml
# docker-compose.yml
api-server:
  image: apache/airflow:3.0.0
  command: api-server
  volumes:
    - ./webserver_config.py:/opt/airflow/webserver_config.py:ro
  environment:
    AIRFLOW__CORE__AUTH_MANAGER: airflow.providers.fab.auth_manager.FabAuthManager
```

---

## Example 5: Custom Auth Manager Class Skeleton

This skeleton shows the full interface you need to implement to create a custom Auth Manager. Fill in the methods with your organization's identity service.

```python
# plugins/my_auth_manager.py
"""
Custom Auth Manager skeleton.

To activate:
  [core]
  auth_manager = my_auth_manager.MyOrgAuthManager

This example uses a hypothetical internal SSO service.
Replace _call_sso_service() with your actual identity provider client.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flask import redirect, request, session, url_for

from airflow.auth.managers.base_auth_manager import BaseAuthManager, ResourceMethod

if TYPE_CHECKING:
    from airflow.auth.managers.models.resource_details import (
        AccessView,
        ConnectionDetails,
        DagDetails,
        DatasetDetails,
        PoolDetails,
        VariableDetails,
    )

log = logging.getLogger(__name__)


class MyOrgAuthManager(BaseAuthManager):
    """
    Auth Manager that validates sessions against an internal SSO service.
    """

    # ── Login / session ────────────────────────────────────────────────────────

    def get_url_login(self, **kwargs) -> str:
        """Redirect unauthenticated users here."""
        return "/my-org-login"

    def get_url_logout(self) -> str:
        return "/my-org-logout"

    def is_logged_in(self) -> bool:
        return bool(session.get("sso_user"))

    def get_user(self):
        return session.get("sso_user")

    def get_user_name(self) -> str:
        user = self.get_user()
        return user["username"] if user else ""

    def get_user_display_name(self) -> str:
        user = self.get_user()
        return user.get("display_name", self.get_user_name())

    # ── Authorization helpers ──────────────────────────────────────────────────

    def _has_role(self, *roles: str) -> bool:
        """Return True if the current user has any of the given roles."""
        user = self.get_user()
        if not user:
            return False
        user_roles = set(user.get("roles", []))
        return bool(user_roles & set(roles))

    # ── DAG permissions ────────────────────────────────────────────────────────

    def is_authorized_dag(
        self,
        method: ResourceMethod,
        details: DagDetails | None = None,
        user=None,
    ) -> bool:
        if method in ("GET", "HEAD"):
            return self._has_role("admin", "op", "user", "viewer")
        if method in ("POST", "PUT", "PATCH"):
            return self._has_role("admin", "op")
        if method == "DELETE":
            return self._has_role("admin")
        return False

    # ── Connection permissions ─────────────────────────────────────────────────

    def is_authorized_connection(
        self,
        method: ResourceMethod,
        details: ConnectionDetails | None = None,
        user=None,
    ) -> bool:
        return self._has_role("admin", "op")

    # ── Variable permissions ───────────────────────────────────────────────────

    def is_authorized_variable(
        self,
        method: ResourceMethod,
        details: VariableDetails | None = None,
        user=None,
    ) -> bool:
        if method == "GET":
            return self._has_role("admin", "op", "user")
        return self._has_role("admin", "op")

    # ── Pool permissions ───────────────────────────────────────────────────────

    def is_authorized_pool(
        self,
        method: ResourceMethod,
        details: PoolDetails | None = None,
        user=None,
    ) -> bool:
        return self._has_role("admin", "op")

    # ── View permissions ───────────────────────────────────────────────────────

    def is_authorized_view(self, access_view: AccessView) -> bool:
        return self.is_logged_in()
```

Register in `airflow.cfg`:

```ini
[core]
auth_manager = my_auth_manager.MyOrgAuthManager
```

---

## 📂 Navigation
⬅️ **Prev: [Interview Q&A](./Interview_QA.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Edge Executor](../34_Edge_Executor/Theory.md)**
