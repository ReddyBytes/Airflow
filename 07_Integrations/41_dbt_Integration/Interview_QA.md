# Airflow + dbt Integration — Interview Q&A

Questions that come up when discussing dbt orchestration and the modern data stack
in data engineering interviews.

---

## Q1. Why use Airflow to orchestrate dbt instead of running dbt on a schedule directly?

**Answer:**
dbt can run on a schedule using dbt Cloud or cron, but Airflow adds:

- **Dependency management** — trigger dbt only after upstream data has landed
  (using a Sensor or Asset dependency)
- **Failure handling** — retry failed models, send alerts on test failures, branch
  based on outcomes
- **Parameter passing** — dynamically pass `execution_date`, target schema, or
  environment flags to dbt at runtime
- **Pipeline integration** — dbt is one step in a larger pipeline (extract → load → transform → notify)
- **Backfill control** — re-run historical dbt runs for specific date ranges

Running dbt standalone is fine for simple cases. Airflow becomes valuable when dbt
is part of a larger orchestrated system.

---

## Q2. What is astronomer-cosmos and why would you use it over a simple BashOperator?

**Answer:**
`astronomer-cosmos` is an open-source library that parses your dbt project and
automatically generates one Airflow task per dbt model. It uses `ref()` and `source()`
calls to derive task dependencies.

**Advantages over BashOperator:**

| BashOperator | astronomer-cosmos |
|---|---|
| One task for entire dbt run | One task per model |
| Retry reruns everything | Retry reruns only the failed model |
| No lineage in Airflow UI | Full model graph visible in Airflow UI |
| Manual `--select` to scope | Automatic dependency graph |

Use BashOperator for small projects (< 10 models) or when setup simplicity matters.
Use cosmos for production with 10+ models where visibility and granular retries are important.

---

## Q3. How do you pass the Airflow execution date to a dbt run?

**Answer:**
Use dbt's `--vars` flag with Airflow's Jinja templating:

```python
BashOperator(
    task_id="dbt_run",
    bash_command="""
        dbt run \
          --vars '{"execution_date": "{{ ds }}"}' \
          --project-dir /opt/dbt/my_project
    """,
)
```

In the dbt model:
```sql
WHERE order_date = '{{ var("execution_date") }}'
```

This makes the dbt run idempotent — re-running for a specific date always produces
the same result, which is critical for backfills.

---

## Q4. How do you handle dbt test failures in an Airflow pipeline?

**Answer:**
Default behaviour: `dbt test` fails → task fails → DAG run fails. This is usually correct.

For more control — alert on failure but let downstream tasks continue:

```python
dbt_test = BashOperator(
    task_id="dbt_test",
    bash_command="dbt test --store-failures 2>&1 | tee /tmp/output.txt; exit ${PIPESTATUS[0]}",
    trigger_rule="all_done",  # run even if dbt_run failed
)

@task(trigger_rule="one_failed")
def handle_failure():
    # Send Slack alert, log failures, etc.
    pass

@task(trigger_rule="all_success")
def mark_complete():
    pass

dbt_run >> dbt_test >> [handle_failure(), mark_complete()]
```

Using `--store-failures` saves the failing rows to your warehouse for debugging.

---

## Q5. Where should dbt profiles be stored when running from Airflow?

**Answer:**
Never store dbt profiles (which contain warehouse credentials) in the DAG code or
in the Docker image as plain text.

Recommended approaches:

1. **Airflow Connections** — create a connection in Airflow for the warehouse; cosmos
   reads it directly via `profile_mapping` (e.g., `PostgresUserPasswordProfileMapping`)
2. **Secrets Manager backend** — store credentials in AWS Secrets Manager or HashiCorp
   Vault; Airflow's SecretsManagerBackend fetches them at runtime
3. **Environment variables** — inject credentials as env vars via Kubernetes Secrets
   or MWAA environment config; reference in `profiles.yml` with `{{ env_var() }}`

Cosmos makes option 1 the cleanest — it abstracts the profile entirely.

---

## Q6. What is the difference between `DbtDag` and `DbtTaskGroup` in cosmos?

**Answer:**

| | DbtDag | DbtTaskGroup |
|---|---|---|
| What it creates | An entire DAG | A task group within a DAG |
| Use when | dbt transformation is the whole pipeline | dbt is one step in a larger pipeline |
| Flexibility | Less (cosmos controls the DAG structure) | More (you control surrounding tasks) |

`DbtDag` is the quickest way to get all dbt models as Airflow tasks.
`DbtTaskGroup` is more common in production where the pattern is:
extract → load → `DbtTaskGroup` → notify/export.

---

## Q7. How would you run only a subset of dbt models from Airflow?

**Answer:**
Two approaches:

**BashOperator with `--select`:**
```python
BashOperator(
    bash_command="dbt run --select path:models/marts --project-dir /opt/dbt/my_project",
)
```

**cosmos with `RenderConfig`:**
```python
from cosmos import RenderConfig

DbtTaskGroup(
    group_id="marts_only",
    project_config=ProjectConfig(dbt_project_path=...),
    render_config=RenderConfig(select=["path:models/marts"]),
    profile_config=profile_config,
)
```

dbt selector syntax:
- `+my_model` — model + all upstream
- `my_model+` — model + all downstream
- `path:models/marts` — all models in a folder
- `tag:daily` — all models tagged `daily`

---

## Q8. How do you make a dbt run idempotent for backfills?

**Answer:**
Idempotency means re-running for a given date always produces the same result:

1. **Pass `execution_date` as a dbt variable** — so the model filters to the correct
   date range rather than processing "today"
2. **Use incremental models with `is_incremental()`** in dbt — they delete and reinsert
   for the target date rather than appending
3. **Use `--full-refresh` flag when needed** — forces a complete rebuild for the model

```python
# Backfill-safe run
BashOperator(
    bash_command="dbt run --vars '{\"start_date\": \"{{ ds }}\", \"end_date\": \"{{ next_ds }}\"}'"
)
```

Without this, backfilling will process "today's" data for every historical run,
producing wrong results.

---

## Q9. What are the most common mistakes when integrating Airflow and dbt?

**Answer:**

| Mistake | Fix |
|---|---|
| Not running `dbt deps` first | Add `dbt deps` as a task before `dbt run` |
| Hardcoding profiles.yml credentials | Use Airflow connections or Secrets Manager |
| No `dbt test` step | Always test after run — silent data quality failures are worse than pipeline failures |
| Not passing `execution_date` | Results are not idempotent, backfills produce wrong data |
| One BashOperator for 50 models | Use cosmos for visibility and granular retries |
| Ignoring `--store-failures` | Failing rows lost — impossible to debug data quality issues |

---

## 📂 Navigation

| | |
|---|---|
| **Theory** | [Theory.md](./Theory.md) |
| **Cheatsheet** | [Cheatsheet.md](./Cheatsheet.md) |
| **Code Example** | [Code_Example.md](./Code_Example.md) |
| **Next: Spark** | [42_Spark_Integration/Theory.md](../42_Spark_Integration/Theory.md) |
| **Parent: Integrations** | [Readme.md](../Readme.md) |
