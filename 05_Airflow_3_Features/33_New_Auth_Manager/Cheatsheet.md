# New Auth Manager — Cheatsheet

## Navigation
⬅️ **Prev: [DAG Versioning](../32_DAG_Versioning/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Edge Executor](../34_Edge_Executor/Theory.md)**

---

## Available Auth Managers

| Auth Manager | Package | Use Case |
|-------------|---------|----------|
| `SimpleAuthManager` | Built-in | Dev/testing only — config-file users |
| `FabAuthManager` | `apache-airflow-providers-fab` | Production — OAuth, LDAP, DB users |
| Custom | Your own class | Enterprise SSO, custom permissions |

---

## Config: Set Auth Manager

```ini
# airflow.cfg

# Development (default)
[core]
auth_manager = airflow.auth.managers.simple.SimpleAuthManager

# Production (FAB — Airflow 2 compatible)
[core]
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager

# Custom
[core]
auth_manager = my_package.my_module.MyAuthManager
```

---

## Simple Auth Manager Setup

```ini
[core]
auth_manager = airflow.auth.managers.simple.SimpleAuthManager

[simple_auth_manager]
admin_users = admin,alice
```

```bash
# Set passwords via environment variables
export AIRFLOW_SIMPLE_AUTH_MANAGER_PASSWORDS_ADMIN=securepass
export AIRFLOW_SIMPLE_AUTH_MANAGER_PASSWORDS_ALICE=alicepass
```

---

## FAB Auth Manager: OAuth Example

```ini
[core]
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager

[fab]
auth_type = AUTH_OAUTH
oauth_providers = [
    {
        "name": "google",
        "icon": "fa-google",
        "token_key": "access_token",
        "remote_app": {
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "api_base_url": "https://www.googleapis.com/oauth2/v2/",
            "access_token_url": "https://accounts.google.com/o/oauth2/token",
            "authorize_url": "https://accounts.google.com/o/oauth2/auth",
            "request_token_url": null,
            "client_kwargs": {"scope": "email profile"}
        }
    }
]
```

---

## FAB RBAC Roles Table

| Role | DAGs | Connections | Variables | Admin |
|------|------|-------------|-----------|-------|
| `Admin` | Full | Full | Full | Yes |
| `Op` | Trigger, clear | View | View | No |
| `User` | Trigger, view | No | View | No |
| `Viewer` | View only | No | No | No |
| `Public` | None | None | None | No |

---

## JWT Token API Authentication

```python
# Get token
import requests

resp = requests.post(
    "http://airflow:8080/auth/token",
    json={"username": "admin", "password": "admin"},
)
token = resp.json()["access_token"]
refresh_token = resp.json()["refresh_token"]

# Use token
headers = {"Authorization": f"Bearer {token}"}
requests.get("http://airflow:8080/api/v2/dags", headers=headers)

# Refresh
resp = requests.post(
    "http://airflow:8080/auth/token/refresh",
    json={"refresh_token": refresh_token},
)
new_token = resp.json()["access_token"]
```

---

## JWT Config

```ini
[api_server]
access_token_lifetime = 900       # 15 minutes (seconds)
refresh_token_lifetime = 2592000  # 30 days (seconds)
```

---

## Migrating from Airflow 2 FAB Auth

```bash
# 1. Install FAB provider
pip install apache-airflow-providers-fab

# 2. Update config
# [core]
# auth_manager = airflow.providers.fab.auth_manager.FabAuthManager

# 3. Run DB migration (preserves existing users/roles)
airflow db migrate

# 4. Verify
airflow users list
```

---

## Custom Auth Manager Skeleton

```python
from airflow.auth.managers.base_auth_manager import BaseAuthManager

class MyAuthManager(BaseAuthManager):

    def is_logged_in(self) -> bool: ...
    def get_user(self): ...
    def is_authorized_dag(self, method, details=None) -> bool: ...
    def is_authorized_connection(self, method, details=None) -> bool: ...
    def is_authorized_variable(self, method, details=None) -> bool: ...
    def is_authorized_pool(self, method, details=None) -> bool: ...
    def is_authorized_asset(self, method, details=None) -> bool: ...
    def get_url_login(self, **kwargs) -> str: ...
    def get_url_logout(self) -> str: ...
```

---

## Navigation
⬅️ **Prev: [DAG Versioning](../32_DAG_Versioning/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Edge Executor](../34_Edge_Executor/Theory.md)**
