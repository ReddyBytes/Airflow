# Airflow CLI — Complete Command Reference

All major Airflow CLI commands with syntax, descriptions, common flags, and example usage.

Run `airflow --help` to see all command groups. Run `airflow <command> --help` for flags on any command.

---

## DAG Commands

### `airflow dags list`
List all DAGs that the scheduler has parsed.

```bash
# Basic list
airflow dags list

# Output as JSON
airflow dags list --output json

# Include paused DAGs in output (they are included by default)
airflow dags list --output table
```

---

### `airflow dags trigger`
Manually trigger a DAG run.

```bash
# Trigger with today as logical date
airflow dags trigger my_dag_id

# Trigger with a specific logical date
airflow dags trigger my_dag_id --exec-date 2024-01-15

# Trigger with a specific run ID
airflow dags trigger my_dag_id --run-id manual__2024-01-15

# Trigger and pass configuration as JSON
airflow dags trigger my_dag_id --conf '{"env": "prod", "batch_size": 1000}'
```

---

### `airflow dags pause`
Pause a DAG — the scheduler will not create new runs.

```bash
airflow dags pause my_dag_id

# Pause all DAGs matching a regex pattern
airflow dags pause --dag-regex "etl_.*"
```

---

### `airflow dags unpause`
Unpause a DAG — the scheduler resumes creating runs.

```bash
airflow dags unpause my_dag_id

# Unpause with regex
airflow dags unpause --dag-regex "etl_.*"
```

---

### `airflow dags backfill`
Create DAG runs for a range of historical dates.

```bash
# Run the DAG for every date from 2024-01-01 to 2024-01-31
airflow dags backfill my_dag_id \
  --start-date 2024-01-01 \
  --end-date 2024-01-31

# Backfill without actually running (dry run — shows what would run)
airflow dags backfill my_dag_id \
  --start-date 2024-01-01 \
  --end-date 2024-01-07 \
  --dry-run

# Backfill and rerun tasks that already succeeded
airflow dags backfill my_dag_id \
  --start-date 2024-01-01 \
  --end-date 2024-01-07 \
  --reset-dagruns

# Backfill in parallel (run N dag runs at the same time)
airflow dags backfill my_dag_id \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --max-active-runs 4
```

**Caution:** `backfill` creates real runs and executes real tasks. Use `--dry-run` first to preview.

---

### `airflow dags delete`
Delete a DAG and all its associated metadata (runs, task instances, logs).

```bash
# Interactive confirmation prompt
airflow dags delete my_dag_id

# Skip confirmation
airflow dags delete my_dag_id --yes
```

**Caution:** This is irreversible. It deletes all historical run data for the DAG from the metadata DB.

---

### `airflow dags show`
Display the DAG as an ASCII graph (requires `graphviz` installed).

```bash
airflow dags show my_dag_id

# Save as PNG image
airflow dags show my_dag_id --save my_dag.png

# Output as DOT format (for Graphviz tools)
airflow dags show my_dag_id --imgcat
```

---

### `airflow dags test`
Execute one full DAG run locally (bypasses the scheduler, runs tasks inline).

```bash
# Test the DAG for a specific logical date
airflow dags test my_dag_id 2024-01-15

# Test with config JSON
airflow dags test my_dag_id 2024-01-15 --conf '{"key": "value"}'
```

**Note:** `dags test` runs tasks in the local process, sequentially. It still reads real connections and writes real XComs. It is useful for verifying DAG logic without going through the scheduler.

---

### `airflow dags state`
Get the state of a specific DAG run.

```bash
airflow dags state my_dag_id 2024-01-15
# Output: success / failed / running / queued
```

---

### `airflow dags list-runs`
List all DAG runs (or runs for a specific DAG).

```bash
# All runs for a specific DAG
airflow dags list-runs --dag-id my_dag_id

# Filter by state
airflow dags list-runs --dag-id my_dag_id --state failed

# Limit results
airflow dags list-runs --dag-id my_dag_id --no-backfill --limit 10

# Output as JSON
airflow dags list-runs --dag-id my_dag_id --output json
```

---

### `airflow dags report`
Show a summary report of all DAGs.

```bash
airflow dags report
```

---

## Task Commands

### `airflow tasks list`
List all tasks in a DAG.

```bash
airflow tasks list my_dag_id

# Show tree view of task dependencies
airflow tasks list my_dag_id --tree
```

---

### `airflow tasks run`
Run a specific task instance (via the executor, as if the scheduler triggered it).

```bash
airflow tasks run my_dag_id my_task_id 2024-01-15

# Run a specific try number
airflow tasks run my_dag_id my_task_id 2024-01-15 --job-id 123

# Ignore all dependencies (run even if upstream failed)
airflow tasks run my_dag_id my_task_id 2024-01-15 --ignore-all-dependencies

# Ignore previous task instance (re-run even if succeeded)
airflow tasks run my_dag_id my_task_id 2024-01-15 --force
```

---

### `airflow tasks test`
Run a task in local mode (no state recorded, no XCom interaction by default).

```bash
# Test a task for a specific date
airflow tasks test my_dag_id my_task_id 2024-01-15

# Pass additional configuration
airflow tasks test my_dag_id my_task_id 2024-01-15 \
  --conf '{"param": "value"}'
```

**Key difference from `tasks run`:** `tasks test` does not write task state to the metadata DB, so it is purely for local testing/debugging. Logs are printed to stdout.

---

### `airflow tasks clear`
Clear (reset) task instances so they can be re-run.

```bash
# Clear a specific task across all runs in a date range
airflow tasks clear my_dag_id \
  --task-regex my_task_id \
  --start-date 2024-01-01 \
  --end-date 2024-01-31

# Clear all tasks in a DAG for a date range
airflow tasks clear my_dag_id \
  --start-date 2024-01-15 \
  --end-date 2024-01-15

# Include downstream tasks (clear my_task and everything after it)
airflow tasks clear my_dag_id \
  --task-regex my_task_id \
  --downstream \
  --start-date 2024-01-15

# Include upstream tasks (clear my_task and everything before it)
airflow tasks clear my_dag_id \
  --task-regex my_task_id \
  --upstream \
  --start-date 2024-01-15

# Skip confirmation prompt
airflow tasks clear my_dag_id \
  --task-regex my_task_id \
  --start-date 2024-01-15 \
  --yes

# Only clear failed tasks (leave successful ones alone)
airflow tasks clear my_dag_id \
  --start-date 2024-01-15 \
  --only-failed
```

---

### `airflow tasks state`
Get the current state of a task instance.

```bash
airflow tasks state my_dag_id my_task_id 2024-01-15
# Output: success / failed / running / queued / skipped / up_for_retry
```

---

### `airflow tasks states-for-dag-run`
Get the states of all task instances for a specific DAG run.

```bash
airflow tasks states-for-dag-run my_dag_id scheduled__2024-01-15T00:00:00+00:00
```

---

## DB Commands

### `airflow db init`
Initialize the metadata database (run once on first install).

```bash
airflow db init
```

---

### `airflow db upgrade`
Apply any pending database migrations (run after upgrading Airflow version).

```bash
airflow db upgrade
```

---

### `airflow db check`
Check that the database is reachable and migrations are up to date.

```bash
airflow db check
```

---

### `airflow db reset`
Drop and recreate all tables in the metadata database.

```bash
# Interactive confirmation
airflow db reset

# Skip confirmation — DESTRUCTIVE
airflow db reset --yes
```

**Caution:** `db reset` deletes all DAG runs, task states, connections, variables, and users. Only use in development.

---

### `airflow db shell`
Open an interactive SQL shell connected to the metadata database.

```bash
airflow db shell
```

---

### `airflow db clean`
Remove old records from the database (keep only N most recent runs per DAG).

```bash
# Preview what would be deleted
airflow db clean --clean-before-timestamp "2024-01-01" --dry-run

# Delete records older than a timestamp
airflow db clean --clean-before-timestamp "2024-01-01" --yes
```

---

## User Commands

### `airflow users create`
Create a new Airflow user.

```bash
airflow users create \
  --username admin \
  --password admin123 \
  --firstname John \
  --lastname Smith \
  --role Admin \
  --email john@example.com

# Roles: Admin, User, Op, Viewer, Public
```

---

### `airflow users list`
List all users.

```bash
airflow users list

# Output as JSON
airflow users list --output json
```

---

### `airflow users delete`
Delete a user.

```bash
airflow users delete --username john_smith
```

---

### `airflow users add-role`
Add a role to an existing user.

```bash
airflow users add-role --username john_smith --role Op
```

---

### `airflow users remove-role`
Remove a role from a user.

```bash
airflow users remove-role --username john_smith --role Op
```

---

## Pool Commands

### `airflow pools set`
Create or update a pool.

```bash
# Create a pool with 5 slots
airflow pools set db_pool 5 "Max 5 concurrent database connections"

# Syntax: airflow pools set <name> <slots> <description>
```

---

### `airflow pools get`
Get details of a specific pool.

```bash
airflow pools get db_pool
```

---

### `airflow pools delete`
Delete a pool.

```bash
airflow pools delete db_pool
```

---

### `airflow pools list`
List all pools with their slot usage.

```bash
airflow pools list

# Output as JSON
airflow pools list --output json
```

---

### `airflow pools import`
Import pools from a JSON file (bulk creation).

```bash
airflow pools import /path/to/pools.json
```

**Example `pools.json`:**
```json
{
  "db_pool":  { "slots": 5,  "description": "Database connections" },
  "api_pool": { "slots": 10, "description": "External API rate limiter" },
  "ml_pool":  { "slots": 2,  "description": "ML training resource pool" }
}
```

---

### `airflow pools export`
Export all pools to a JSON file.

```bash
airflow pools export /path/to/pools_backup.json
```

---

## Variable Commands

### `airflow variables set`
Create or update a variable.

```bash
# Basic set
airflow variables set my_key "my_value"

# Set a variable with JSON value (use -j flag)
airflow variables set db_config '{"host": "localhost", "port": 5432}' --json
```

---

### `airflow variables get`
Get the value of a variable.

```bash
airflow variables get my_key

# Get and deserialize JSON value
airflow variables get db_config --json

# Return a default if key does not exist (in Python code)
# Variable.get("my_key", default_var="fallback_value")
```

---

### `airflow variables delete`
Delete a variable.

```bash
airflow variables delete my_key
```

---

### `airflow variables list`
List all variable keys.

```bash
airflow variables list

# Output as JSON
airflow variables list --output json
```

---

### `airflow variables import`
Import variables from a JSON file.

```bash
airflow variables import /path/to/variables.json
```

**Example `variables.json`:**
```json
{
  "env": "production",
  "slack_webhook": "https://hooks.slack.com/...",
  "ml_accuracy_threshold": "0.85"
}
```

---

### `airflow variables export`
Export all variables to a JSON file.

```bash
airflow variables export /path/to/variables_backup.json
```

**Warning:** Variable values may contain secrets. Do not commit the exported file to version control without removing sensitive values.

---

## Connection Commands

### `airflow connections add`
Add a new connection.

```bash
# Add a Postgres connection
airflow connections add postgres_default \
  --conn-type postgres \
  --conn-host localhost \
  --conn-login airflow \
  --conn-password airflow \
  --conn-schema airflow \
  --conn-port 5432

# Add an HTTP connection
airflow connections add my_api \
  --conn-type http \
  --conn-host api.example.com \
  --conn-schema https \
  --conn-port 443

# Add a connection with extra JSON config
airflow connections add s3_default \
  --conn-type aws \
  --conn-extra '{"region_name": "us-east-1"}'

# Add using a URI (shortcut for all fields in one string)
airflow connections add my_pg \
  --conn-uri "postgresql://user:pass@host:5432/dbname"
```

---

### `airflow connections get`
Get details of a specific connection.

```bash
airflow connections get postgres_default

# Output as JSON
airflow connections get postgres_default --output json
```

---

### `airflow connections delete`
Delete a connection.

```bash
airflow connections delete postgres_default
```

---

### `airflow connections list`
List all connections.

```bash
airflow connections list

# Output as JSON
airflow connections list --output json

# Filter by connection type
airflow connections list --conn-type postgres
```

---

### `airflow connections import`
Import connections from a JSON or YAML file.

```bash
airflow connections import /path/to/connections.json
```

---

### `airflow connections export`
Export connections to a file.

```bash
airflow connections export /path/to/connections_backup.json
```

**Warning:** Exported connections may contain plaintext passwords. Handle with care. Never commit to version control.

---

## Service Commands

### `airflow webserver`
Start the Airflow webserver.

```bash
# Start on default port 8080
airflow webserver

# Start on a specific port
airflow webserver --port 8080

# Start with a specific number of gunicorn workers
airflow webserver --workers 4

# Start in debug mode
airflow webserver --debug

# Specify log file
airflow webserver --log-file /var/log/airflow/webserver.log
```

---

### `airflow scheduler`
Start the Airflow scheduler.

```bash
# Start the scheduler
airflow scheduler

# Start with a specific number of threads
airflow scheduler --num-runs 100

# Specify log file
airflow scheduler --log-file /var/log/airflow/scheduler.log
```

---

### `airflow triggerer`
Start the Airflow triggerer (handles deferrable operators).

```bash
airflow triggerer

# Set the capacity (max concurrent triggers)
airflow triggerer --capacity 1000
```

---

### `airflow celery worker`
Start a Celery worker (CeleryExecutor only).

```bash
# Start a worker on the default queue
airflow celery worker

# Start a worker on specific queues
airflow celery worker --queues default,high_priority,gpu_queue

# Set worker concurrency (number of parallel tasks per worker)
airflow celery worker --concurrency 16

# Set log level
airflow celery worker --loglevel info
```

---

### `airflow celery flower`
Start the Celery Flower monitoring UI.

```bash
airflow celery flower

# Run on a specific port
airflow celery flower --port 5555

# Set address to bind
airflow celery flower --broker-api http://guest:guest@localhost:15672/api/
```

---

### `airflow celery stop`
Gracefully stop all Celery workers.

```bash
airflow celery stop
```

---

## Info and Version Commands

```bash
# Print Airflow version
airflow version

# Print full configuration info
airflow info

# Print configuration with all settings and their sources
airflow config list

# Get a specific config value
airflow config get-value core executor

# Print all dags directory paths
airflow config get-value core dags_folder
```

---

## Useful Patterns

### Check DAG Health Before Deployment

```bash
# Parse a DAG file and check for syntax errors
python my_dag.py

# Or use airflow to verify
airflow dags list-import-errors

# List any DAG import errors
airflow dags list-import-errors --output table
```

---

### Full Environment Bootstrap Script

```bash
#!/bin/bash
# bootstrap_airflow.sh — run once after fresh install

set -e

echo "Initializing database..."
airflow db init

echo "Creating admin user..."
airflow users create \
  --username admin \
  --password admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com

echo "Creating pools..."
airflow pools import /opt/airflow/config/pools.json

echo "Creating variables..."
airflow variables import /opt/airflow/config/variables.json

echo "Creating connections..."
airflow connections import /opt/airflow/config/connections.json

echo "Airflow bootstrap complete."
```

---

### DAG Maintenance Script

```bash
#!/bin/bash
# Pause, clear failed tasks, and unpause a DAG

DAG_ID="my_etl_dag"
DATE="2024-01-15"

echo "Pausing DAG..."
airflow dags pause $DAG_ID

echo "Clearing all failed tasks for $DATE..."
airflow tasks clear $DAG_ID \
  --start-date $DATE \
  --end-date $DATE \
  --only-failed \
  --yes

echo "Unpausing DAG..."
airflow dags unpause $DAG_ID

echo "Triggering backfill run..."
airflow dags trigger $DAG_ID --exec-date $DATE
```
