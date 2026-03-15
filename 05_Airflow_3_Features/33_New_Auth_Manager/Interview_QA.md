# New Auth Manager — Interview Q&A

## 📂 Navigation
⬅️ **Prev: [DAG Versioning](../32_DAG_Versioning/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Edge Executor](../34_Edge_Executor/Theory.md)**

---

## Q1: What is the Auth Manager in Airflow 3?

The **Auth Manager** is a pluggable interface in Airflow 3 that handles two responsibilities:

1. **Authentication** — verifying who you are (login, tokens, SSO)
2. **Authorization** — deciding what you are allowed to do (view DAGs, trigger runs, edit connections)

In Airflow 2, Flask-AppBuilder (FAB) was the hardcoded authentication and authorization framework. You could not replace it without patching Airflow's internals.

Airflow 3 extracts auth into an abstract `BaseAuthManager` class. Any class that implements this interface can be swapped in via configuration, with no code changes to Airflow itself. Shipped implementations include `SimpleAuthManager` (development) and `FabAuthManager` (production FAB-based auth). You can also write your own.

---

## Q2: What is SimpleAuthManager and when should you use it?

`SimpleAuthManager` is a minimal auth manager included in the Airflow core package. It reads usernames, passwords, and roles from the `airflow.cfg` config file or environment variables.

**When to use it:**
- Local development environments
- CI/CD pipelines running Airflow tests
- Docker Compose quick-start setups where you just need to get in

**When NOT to use it:**
- Any production environment
- Anything exposed to the internet
- Any multi-user environment where you need real RBAC

```ini
# airflow.cfg — enable SimpleAuthManager
[core]
auth_manager = airflow.auth.managers.simple.SimpleAuthManager

[simple_auth_manager]
# Define users: username:password:role
users = admin:admin123:admin,viewer:view456:viewer
```

Passwords are stored in plain text in config. There is no user database, no password hashing, no session management beyond a basic cookie. It is a development convenience, not a security solution.

---

## Q3: What is FabAuthManager and how does it differ from Airflow 2's FAB integration?

`FabAuthManager` is the production-ready auth manager that wraps Flask-AppBuilder — the same auth backend used in Airflow 2. The difference is that in Airflow 3, FAB is now:

- **Optional** — you must explicitly install `apache-airflow-providers-fab`
- **Configurable** — you set `auth_manager = airflow.providers.fab.auth_manager.FabAuthManager`
- **Isolated** — FAB code lives in the provider package, not in Airflow core
- **Replaceable** — if FAB does not meet your needs, you can replace it without forking Airflow

Functionally, `FabAuthManager` gives you:
- Web-based user management UI (Admin > Security)
- Role-based access control with fine-grained permissions
- Built-in OAuth2 / OpenID Connect support (GitHub, Google, Azure AD, Okta)
- LDAP / Active Directory integration
- Multiple authentication backends in sequence

```bash
pip install apache-airflow-providers-fab
```

```ini
[core]
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager
```

---

## Q4: What roles are available out of the box in FabAuthManager?

FabAuthManager ships with five default roles:

| Role | Description |
|------|-------------|
| **Admin** | Full access to everything, including user management |
| **Op** | Can manage DAGs, connections, variables, and pools; cannot manage users |
| **User** | Can trigger and view DAGs and runs; cannot change connections or variables |
| **Viewer** | Read-only access to DAGs and runs; cannot trigger anything |
| **Public** | No authentication required; anonymous access (disabled by default) |

You can create custom roles with granular permissions, e.g., a role that can only view DAGs in a specific namespace or only trigger a subset of DAGs.

---

## Q5: How does DAG-level access control work?

In Airflow 3 with FabAuthManager, you can restrict which users can see or interact with specific DAGs.

**Method 1 — `access_control` DAG parameter:**

```python
with DAG(
    dag_id="finance_pipeline",
    access_control={
        "Finance Team": {"can_read", "can_edit", "can_delete"},
        "Data Viewer":  {"can_read"},
    },
) as dag:
    ...
```

Users in the "Finance Team" role can read, edit, and delete this DAG. Users in "Data Viewer" can only see it. All other roles have no access to this DAG.

**Method 2 — Via the UI:** Admin > Security > DAG Access.

**Method 3 — Namespace-based routing:** Some organizations create one role per team with resource-level permissions set to only that team's DAG IDs.

---

## Q6: How do you configure OAuth2 authentication with FabAuthManager?

OAuth2 lets users log in with their Google, GitHub, Azure AD, or Okta accounts instead of a separate Airflow password.

```python
# webserver_config.py (still used by FabAuthManager in Airflow 3)
from airflow.auth.managers.fab.security_manager.override import FabAirflowSecurityManagerOverride
from airflow.www.security import AirflowSecurityManager
from flask_appbuilder.security.manager import AUTH_OAUTH

AUTH_TYPE = AUTH_OAUTH

OAUTH_PROVIDERS = [
    {
        "name": "google",
        "icon": "fa-google",
        "token_key": "access_token",
        "remote_app": {
            "client_id": "YOUR_GOOGLE_CLIENT_ID",
            "client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
            "api_base_url": "https://www.googleapis.com/oauth2/v2/",
            "client_kwargs": {"scope": "email profile"},
            "access_token_url": "https://accounts.google.com/o/oauth2/token",
            "authorize_url": "https://accounts.google.com/o/oauth2/auth",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        },
    }
]

# Auto-register new users on first OAuth login
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Viewer"  # Default role for new OAuth users
```

---

## Q7: How do you configure LDAP authentication with FabAuthManager?

```python
# webserver_config.py
from flask_appbuilder.security.manager import AUTH_LDAP

AUTH_TYPE = AUTH_LDAP

AUTH_LDAP_SERVER = "ldap://ldap.yourcompany.com:389"
AUTH_LDAP_USE_TLS = True

# Search base for user lookups
AUTH_LDAP_SEARCH = "ou=users,dc=yourcompany,dc=com"
AUTH_LDAP_SEARCH_FILTER = "(memberOf=cn=airflow-users,ou=groups,dc=yourcompany,dc=com)"

# How to bind for searching (use a service account)
AUTH_LDAP_BIND_USER = "cn=airflow-svc,ou=service,dc=yourcompany,dc=com"
AUTH_LDAP_BIND_PASSWORD = "service_account_password"

# Attribute that contains the username
AUTH_LDAP_UID_FIELD = "sAMAccountName"  # or "uid" for OpenLDAP

# Map LDAP groups to Airflow roles
AUTH_ROLES_MAPPING = {
    "cn=airflow-admins,ou=groups,dc=yourcompany,dc=com":  ["Admin"],
    "cn=airflow-ops,ou=groups,dc=yourcompany,dc=com":     ["Op"],
    "cn=airflow-viewers,ou=groups,dc=yourcompany,dc=com": ["Viewer"],
}

AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Public"
```

---

## Q8: How do you write a custom Auth Manager?

A custom Auth Manager must subclass `BaseAuthManager` and implement the required abstract methods.

The skeleton:

```python
# my_org/auth/custom_auth_manager.py
from airflow.auth.managers.base_auth_manager import BaseAuthManager, ResourceMethod
from airflow.auth.managers.models.resource_details import (
    DagDetails, ConnectionDetails, VariableDetails,
)


class CustomAuthManager(BaseAuthManager):
    """
    Custom auth manager that delegates to an internal SSO service.
    """

    def is_logged_in(self) -> bool:
        """Return True if the current user has a valid session."""
        return self.get_user() is not None

    def get_user(self):
        """Return the current user object from the request context."""
        # Read from your session / JWT token
        from flask import session
        return session.get("current_user")

    def is_authorized_dag(
        self,
        method: ResourceMethod,
        details: DagDetails | None = None,
        user=None,
    ) -> bool:
        """Return True if user may perform `method` on the given DAG."""
        user = user or self.get_user()
        if not user:
            return False
        # Admin can do anything
        if user.role == "admin":
            return True
        # Viewers can only read
        if user.role == "viewer" and method == "GET":
            return True
        return False

    def is_authorized_connection(
        self,
        method: ResourceMethod,
        details: ConnectionDetails | None = None,
        user=None,
    ) -> bool:
        user = user or self.get_user()
        return user is not None and user.role == "admin"

    def is_authorized_variable(
        self,
        method: ResourceMethod,
        details: VariableDetails | None = None,
        user=None,
    ) -> bool:
        user = user or self.get_user()
        return user is not None and user.role in ("admin", "op")

    def get_url_login(self, **kwargs) -> str:
        """URL Airflow should redirect unauthenticated users to."""
        return "/custom-login"

    def get_url_logout(self) -> str:
        return "/custom-logout"
```

Register it in config:
```ini
[core]
auth_manager = my_org.auth.custom_auth_manager.CustomAuthManager
```

---

## Q9: How do you create and manage users with FabAuthManager via CLI?

```bash
# Create a new admin user
airflow users create \
  --username alice \
  --firstname Alice \
  --lastname Smith \
  --role Admin \
  --email alice@example.com \
  --password secret123

# List all users
airflow users list

# Add a role to an existing user
airflow users add-role --username alice --role Op

# Remove a role from a user
airflow users remove-role --username alice --role Viewer

# Delete a user
airflow users delete --username alice

# Create a custom role
airflow roles create DataEngineer

# List permissions on a role
airflow roles list --verbose

# Add permission to a role
airflow roles add-perms \
  --role DataEngineer \
  --resource "DAGs" \
  --action "can_read"
```

---

## Q10: What happens to auth if no auth_manager is configured?

If `auth_manager` is not set in `airflow.cfg`, Airflow 3 uses its **built-in default**, which varies by edition:

- **Open-source Airflow 3 without `providers-fab` installed:** Falls back to `SimpleAuthManager`
- **Open-source Airflow 3 with `providers-fab` installed:** Uses `FabAuthManager`

The recommended practice is to **always explicitly set** `auth_manager` in your configuration rather than relying on the default, so that your deployment behavior is predictable and not affected by which packages happen to be installed.

```ini
# Always be explicit — do not rely on auto-detection
[core]
auth_manager = airflow.providers.fab.auth_manager.FabAuthManager
```

---

## 📂 Navigation
⬅️ **Prev: [DAG Versioning](../32_DAG_Versioning/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [Edge Executor](../34_Edge_Executor/Theory.md)**
