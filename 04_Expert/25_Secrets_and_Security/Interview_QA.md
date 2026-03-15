# 25 — Secrets and Security: Interview Q&A

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

**Q1: What is a secrets backend and why use one instead of storing secrets in the metadata database?**

A secrets backend is an external system (HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager) that Airflow queries when resolving connections and variables. The benefit over metadata DB storage: (1) Secrets never enter the Airflow database, reducing breach surface. (2) The security team controls rotation without Airflow involvement — a new password in Vault is picked up immediately on the next DAG run. (3) Centralized audit logging in the secrets system shows exactly when and which service accessed each secret. (4) Compliance — many regulations require secrets to be stored in certified key management systems, not application databases.

---

**Q2: What is the order Airflow searches for a connection or variable?**

Airflow queries in this exact order: (1) configured secrets backend (e.g., Vault, AWS Secrets Manager), (2) environment variables (`AIRFLOW_CONN_*` for connections, `AIRFLOW_VAR_*` for variables), (3) the metadata database. The first backend that returns a value wins. DAG code (`Variable.get("key")`, `BaseHook.get_connection("conn_id")`) is unchanged regardless of which backend provides the value — the resolution is transparent to DAG authors.

---

**Q3: How do you configure HashiCorp Vault as an Airflow secrets backend?**

Install `apache-airflow-providers-hashicorp`. In `airflow.cfg` (or `AIRFLOW__SECRETS__BACKEND` env var):
```ini
[secrets]
backend = airflow.providers.hashicorp.secrets.vault.VaultBackend
backend_kwargs = {"url": "https://vault.corp.com:8200", "auth_type": "approle", "role_id": "...", "secret_id": "...", "connections_path": "airflow/connections", "variables_path": "airflow/variables", "mount_point": "secret"}
```
Create secrets at `secret/airflow/connections/<conn_id>` with the connection fields as JSON keys (`conn_type`, `host`, `login`, `password`, `port`, `schema`). For variables: `secret/airflow/variables/<var_name>` with `{"value": "secret_value"}`.

---

**Q4: How does AWS Secrets Manager differ from Vault for Airflow?**

The configuration class differs (`SecretsManagerBackend` vs `VaultBackend`), and the auth mechanism is IAM instead of AppRole/token — the Airflow process's IAM role must have `secretsmanager:GetSecretValue` permission. Secret naming uses path prefixes: `airflow/connections/<conn_id>` and `airflow/variables/<var_name>`. Variables in AWS Secrets Manager are stored as plain string secret values (not JSON with a `value` key). AWS also supports automatic rotation with Lambda functions, which works seamlessly with Airflow since it queries the backend on every access.

---

**Q5: What is the Fernet key and what happens if you lose it?**

The Fernet key is a 256-bit symmetric encryption key (AES-128-CBC) used to encrypt connections and variables stored in the metadata database. It is set via `[core] fernet_key` or `AIRFLOW__CORE__FERNET_KEY`. If you lose the key, all encrypted values in the database become unreadable — connections and variables cannot be decrypted, and tasks using them will fail. There is no recovery path without the original key. This is why the Fernet key must be backed up to a secrets manager (not just stored in config files). On new Airflow deployments, generate a key immediately before creating any connections.

---

**Q6: How do you rotate the Fernet key safely?**

Never just replace the key — set both keys comma-separated with the new key first:
```ini
fernet_key = NEW_KEY,OLD_KEY
```
Then run `airflow db migrate`. Airflow re-encrypts all stored values with the new key. After successful migration and verification, remove the old key, leaving only `fernet_key = NEW_KEY`. The two-key approach ensures zero downtime — any value not yet re-encrypted is still decryptable with the old key during the migration window.

---

**Q7: What RBAC roles exist in Airflow 3 and what is the difference between User and Op?**

Built-in roles: **Admin** (full access including user management), **Op** (can trigger, clear, pause/unpause DAGs, and change task states — cannot manage users or edit connections/variables), **User** (can view and trigger DAGs but cannot clear tasks or pause DAGs), **Viewer** (read-only, no triggering), **Public** (unauthenticated access, by default nothing). The practical difference between User and Op: Op can clear failed tasks and retry them; User cannot. Op can also pause DAGs. Both can trigger new runs.

---

**Q8: What is the Auth Manager in Airflow 3 and why was it introduced?**

The Auth Manager is a pluggable abstraction introduced in Airflow 3 that decouples authentication and authorization from the web framework. Previously, RBAC was hardcoded to Flask-AppBuilder, making it impossible to use alternatives (e.g., AWS IAM Identity Center, Okta, corporate LDAP) without patching Airflow. With the Auth Manager interface, providers can ship their own auth implementations — AWS ships an Auth Manager that uses IAM Identity Center for SSO, eliminating the need for local user accounts entirely. Custom Auth Managers can implement `BaseAuthManager` from `airflow.auth.managers`.

---

**Q9: How do you authenticate with the Airflow REST API in production?**

In Airflow 3, the recommended approach is JWT Bearer tokens. First POST to `/auth/token` with credentials to receive a short-lived JWT. Include it as `Authorization: Bearer <token>` in subsequent requests. Configure token lifetime in `airflow.cfg` under `[api] access_token_lifetime_minutes`. For CI/CD systems, use a dedicated service account with minimal permissions (typically `Op` role scoped to specific DAGs via `access_control`). Basic auth is available but should be disabled in production environments (`auth_backends = airflow.api.auth.backend.deny_all` for the basic auth backend).

---

**Q10: How do you restrict a DAG so only certain roles can see or trigger it?**

Use the `access_control` parameter on the DAG:
```python
with DAG(
    dag_id="payments_pipeline",
    access_control={
        "payments_team": {"can_read", "can_edit"},
        "finance_viewers": {"can_read"},
    },
) as dag:
    ...
```
This means only users with the `payments_team` role can read and edit (trigger/clear) the DAG, and `finance_viewers` can only read (view). Users with no matching role cannot see the DAG at all — it disappears from their DAG list. Admin always has access regardless of `access_control`. Custom roles are created in Admin → Security → List Roles.
