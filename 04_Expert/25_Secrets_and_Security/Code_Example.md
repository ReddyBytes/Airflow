# 25 — Secrets and Security: Code Examples

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: HashiCorp Vault Backend — Complete Setup

### Step 1: Install Provider
```bash
pip install apache-airflow-providers-hashicorp
```

### Step 2: Configure Vault Policy
```hcl
# vault-policy-airflow.hcl
path "secret/data/airflow/*" {
  capabilities = ["read", "list"]
}
```

```bash
vault policy write airflow-read vault-policy-airflow.hcl
```

### Step 3: Create AppRole for Airflow
```bash
vault auth enable approle

vault write auth/approle/role/airflow \
    token_policies="airflow-read" \
    token_ttl=1h \
    token_max_ttl=4h

# Get role_id and secret_id
vault read auth/approle/role/airflow/role-id
vault write -f auth/approle/role/airflow/secret-id
```

### Step 4: Write Secrets to Vault
```bash
# Connection: postgres_warehouse
vault kv put secret/airflow/connections/postgres_warehouse \
    conn_type=postgresql \
    host=warehouse.corp.com \
    login=airflow_svc \
    password="p@ssword_prod_123" \
    port=5432 \
    schema=analytics

# Variable: api_key
vault kv put secret/airflow/variables/api_key value="sk_prod_abc123xyz"

# Verify
vault kv get secret/airflow/connections/postgres_warehouse
```

### Step 5: Configure airflow.cfg
```ini
[secrets]
backend = airflow.providers.hashicorp.secrets.vault.VaultBackend
backend_kwargs = {
    "url": "https://vault.corp.com:8200",
    "auth_type": "approle",
    "role_id": "{{ env('VAULT_ROLE_ID') }}",
    "secret_id": "{{ env('VAULT_SECRET_ID') }}",
    "connections_path": "airflow/connections",
    "variables_path": "airflow/variables",
    "config_path": "airflow/config",
    "mount_point": "secret",
    "kv_engine_version": 2
}
```

Or via environment variables (preferred for containers):
```bash
export AIRFLOW__SECRETS__BACKEND="airflow.providers.hashicorp.secrets.vault.VaultBackend"
export AIRFLOW__SECRETS__BACKEND_KWARGS='{
    "url": "https://vault.corp.com:8200",
    "auth_type": "kubernetes",
    "kubernetes_role": "airflow",
    "connections_path": "airflow/connections",
    "variables_path": "airflow/variables",
    "mount_point": "secret",
    "kv_engine_version": 2
}'
```

### Step 6: Verify in DAG (no code change needed)
```python
# dags/test_secrets.py
from airflow.sdk import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from datetime import datetime


def check_secrets():
    # This reads from Vault transparently
    api_key = Variable.get("api_key")
    print(f"Got API key: {api_key[:4]}***")  # Only log first 4 chars!

    # Connection is also from Vault
    from airflow.hooks.base import BaseHook
    conn = BaseHook.get_connection("postgres_warehouse")
    print(f"Got connection: host={conn.host}, user={conn.login}")


with DAG(
    dag_id="test_vault_secrets",
    schedule=None,
    start_date=datetime(2026, 1, 1),
) as dag:
    PythonOperator(task_id="check", python_callable=check_secrets)
```

---

## Example 2: AWS Secrets Manager Backend

### Step 1: Install and Configure
```bash
pip install apache-airflow-providers-amazon
```

```bash
export AIRFLOW__SECRETS__BACKEND="airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend"
export AIRFLOW__SECRETS__BACKEND_KWARGS='{
    "connections_prefix": "airflow/connections",
    "variables_prefix": "airflow/variables",
    "region_name": "us-east-1"
}'
```

### Step 2: Create Secrets in AWS
```bash
# Connection (JSON format)
aws secretsmanager create-secret \
    --name "airflow/connections/postgres_warehouse" \
    --description "Airflow connection for data warehouse" \
    --secret-string '{
        "conn_type": "postgresql",
        "host": "warehouse.us-east-1.rds.amazonaws.com",
        "login": "airflow_svc",
        "password": "prod_password_here",
        "port": 5432,
        "schema": "analytics"
    }'

# Variable (plain string value)
aws secretsmanager create-secret \
    --name "airflow/variables/snowflake_account" \
    --secret-string "xy12345.us-east-1"

# Update a secret (rotation)
aws secretsmanager put-secret-value \
    --secret-id "airflow/connections/postgres_warehouse" \
    --secret-string '{
        "conn_type": "postgresql",
        "host": "warehouse.us-east-1.rds.amazonaws.com",
        "login": "airflow_svc",
        "password": "NEW_rotated_password",
        "port": 5432,
        "schema": "analytics"
    }'
```

### Step 3: IAM Policy for Airflow Role/Instance Profile
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AirflowSecretsRead",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": [
                "arn:aws:secretsmanager:us-east-1:123456789:secret:airflow/*"
            ]
        },
        {
            "Sid": "AirflowSecretsList",
            "Effect": "Allow",
            "Action": "secretsmanager:ListSecrets",
            "Resource": "*",
            "Condition": {
                "StringLike": {
                    "secretsmanager:SecretId": "airflow/*"
                }
            }
        }
    ]
}
```

---

## Example 3: Custom Secrets Backend Implementation

Build a custom backend that reads from a local encrypted JSON file — useful for local development without Vault.

```python
# secrets/local_json_backend.py
"""
Custom secrets backend reading from an encrypted JSON file.

Useful for local development to mimic production secrets backend behavior
without running Vault or AWS.

Setup:
1. Create secrets.json.enc (see encrypt_secrets.py helper below)
2. Configure in airflow.cfg:

   [secrets]
   backend = secrets.local_json_backend.LocalJsonBackend
   backend_kwargs = {"secrets_file": "/path/to/secrets.json.enc", "fernet_key": "..."}

The secrets file format (before encryption):
{
    "connections": {
        "postgres_warehouse": {
            "conn_type": "postgresql",
            "host": "localhost",
            "login": "airflow",
            "password": "dev_password",
            "port": 5432,
            "schema": "airflow_dev"
        }
    },
    "variables": {
        "api_key": "dev_api_key_123",
        "environment": "development"
    }
}
"""
from __future__ import annotations

import json
import logging
from typing import Any

from cryptography.fernet import Fernet

from airflow.secrets import BaseSecretsBackend
from airflow.utils.log.logging_mixin import LoggingMixin

log = logging.getLogger(__name__)


class LocalJsonBackend(BaseSecretsBackend, LoggingMixin):
    """
    Reads connections and variables from a Fernet-encrypted JSON file.

    This backend implements the BaseSecretsBackend interface required by Airflow.
    """

    def __init__(
        self,
        secrets_file: str,
        fernet_key: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.secrets_file = secrets_file
        self.fernet_key = fernet_key
        self._secrets: dict[str, Any] | None = None

    def _load_secrets(self) -> dict[str, Any]:
        """Load and decrypt secrets file. Cached after first load."""
        if self._secrets is not None:
            return self._secrets

        with open(self.secrets_file, "rb") as f:
            data = f.read()

        if self.fernet_key:
            f = Fernet(self.fernet_key.encode())
            data = f.decrypt(data)

        self._secrets = json.loads(data)
        log.info(
            "LocalJsonBackend: loaded %d connections and %d variables from %s",
            len(self._secrets.get("connections", {})),
            len(self._secrets.get("variables", {})),
            self.secrets_file,
        )
        return self._secrets

    def get_connection(self, conn_id: str):
        """
        Return an Airflow Connection object for the given conn_id.

        Returns None if not found (Airflow will try the next backend).
        """
        from airflow.models.connection import Connection

        secrets = self._load_secrets()
        conn_data = secrets.get("connections", {}).get(conn_id)

        if conn_data is None:
            log.debug("LocalJsonBackend: connection '%s' not found", conn_id)
            return None

        log.debug("LocalJsonBackend: found connection '%s'", conn_id)
        return Connection(
            conn_id=conn_id,
            conn_type=conn_data.get("conn_type"),
            host=conn_data.get("host"),
            login=conn_data.get("login"),
            password=conn_data.get("password"),
            port=conn_data.get("port"),
            schema=conn_data.get("schema"),
            extra=json.dumps(conn_data.get("extra", {})) if conn_data.get("extra") else None,
        )

    def get_variable(self, key: str) -> str | None:
        """
        Return a variable value for the given key.

        Returns None if not found.
        """
        secrets = self._load_secrets()
        value = secrets.get("variables", {}).get(key)
        if value is None:
            log.debug("LocalJsonBackend: variable '%s' not found", key)
            return None
        log.debug("LocalJsonBackend: found variable '%s'", key)
        return str(value)

    def get_config(self, key: str) -> str | None:
        """Return a config value for the given key."""
        secrets = self._load_secrets()
        return secrets.get("config", {}).get(key)


# ──────────────────────────────────────────────────────────────────────────────
# Helper script to create the encrypted secrets file
# ──────────────────────────────────────────────────────────────────────────────

def encrypt_secrets_file(
    input_json_path: str,
    output_path: str,
    fernet_key: str,
) -> None:
    """
    Utility to encrypt a plaintext JSON secrets file.

    Usage:
        python -c "
        from secrets.local_json_backend import encrypt_secrets_file
        encrypt_secrets_file('secrets.json', 'secrets.json.enc', 'your_fernet_key')
        "
    """
    from cryptography.fernet import Fernet

    with open(input_json_path, "rb") as f:
        plaintext = f.read()

    fernet = Fernet(fernet_key.encode())
    encrypted = fernet.encrypt(plaintext)

    with open(output_path, "wb") as f:
        f.write(encrypted)

    print(f"Encrypted {input_json_path} → {output_path}")
```

### Registering the Custom Backend
```ini
# airflow.cfg
[secrets]
backend = secrets.local_json_backend.LocalJsonBackend
backend_kwargs = {
    "secrets_file": "/opt/airflow/secrets/secrets.json.enc",
    "fernet_key": "mLJYtF4L35eS_6PxTqFTJaRVKxfD4vK8_5TqDpMoC5o="
}
```

### Testing Any Backend
```bash
# After configuring backend, test resolution:
airflow connections get postgres_warehouse
airflow variables get api_key

# Or in Python:
python -c "
from airflow.hooks.base import BaseHook
conn = BaseHook.get_connection('postgres_warehouse')
print(f'host={conn.host}, login={conn.login}')
"
```
