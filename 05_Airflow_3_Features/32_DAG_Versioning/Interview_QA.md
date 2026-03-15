# DAG Versioning — Interview Q&A

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [New Auth Manager](../33_New_Auth_Manager/Theory.md)**

---

## Q1: What is DAG Versioning in Airflow 3?

DAG Versioning is a feature where Airflow 3 **stores a snapshot of each DAG's serialized structure** whenever the DAG definition changes. Each snapshot is called a **version**. DAG runs are permanently linked to the version that was active when they were scheduled.

Think of it like Git for your DAG's structure — Airflow keeps a history of what the DAG looked like at each point in time.

Before versioning (Airflow 2), if you added a task to a running DAG, all historical runs in the UI would display the new task graph even though those old runs never had that task. This caused confusing visual artifacts — tasks showed as "missing" or "skipped" on runs that predated them.

With versioning, historical runs always show their own version of the graph.

---

## Q2: How are DAG versions stored internally?

When the DAG Processor parses a DAG file and detects a structural change (new task, removed task, changed dependency, changed operator class), it:

1. **Serializes** the new DAG structure to JSON
2. **Hashes** the serialized content
3. **Compares** the hash to the currently stored version
4. If different: **inserts a new version record** in the `dag_version` metadata table
5. Associates the version ID with all new `DagRun` records going forward

The key table is `dag_version`, which stores:
- `dag_id` — which DAG this version belongs to
- `version_number` — monotonically incrementing integer (1, 2, 3...)
- `serialized_dag` — the full JSON snapshot of the DAG structure
- `created_at` — timestamp of when this version was recorded

Existing `DagRun` records keep their `version_number` foreign key, so they always resolve to the correct historical snapshot.

---

## Q3: What counts as a "change" that creates a new DAG version?

A new version is created when the **serialized structure** of the DAG changes. This includes:

**Creates a new version:**
- Adding or removing a task
- Changing task dependencies (the `>>` / `<<` graph edges)
- Changing the operator class on a task (e.g., `PythonOperator` → `BashOperator`)
- Changing the `task_id` of any task
- Adding or removing a `TaskGroup`
- Changing DAG-level parameters like `schedule`, `catchup`, `tags`

**Does NOT create a new version:**
- Changing the Python logic inside a `PythonOperator` callable (the callable name stays the same)
- Adding comments to the DAG file
- Changing environment variables that the DAG reads at parse time (unless they alter task structure)
- Whitespace changes

This distinction matters: you can change your transformation logic without triggering a version bump, but any structural change will create one.

---

## Q4: Can you run a specific older version of a DAG?

Yes. In Airflow 3 you can re-trigger a DAG run and pin it to a specific historical version.

**Via UI:**
1. Open the DAG's detail page
2. Click the **Versions** tab to see the version history
3. Select an older version
4. Click **Trigger Run** from that version's detail view — the run will be associated with that version

**Via CLI:**
```bash
# List available versions for a DAG
airflow dags versions list --dag-id my_pipeline

# Trigger a run using a specific version
airflow dags trigger my_pipeline --dag-version 3
```

The run will execute using the task graph from version 3, not the current version. This is useful for emergency rollbacks when a new deployment broke the DAG.

---

## Q5: How does DAG Versioning differ from Git versioning of DAG files?

They solve overlapping but distinct problems:

| | Git Versioning | Airflow DAG Versioning |
|--|---------------|------------------------|
| **What is stored** | Full DAG Python file | Serialized task graph (structure only) |
| **Tracks** | All file changes (logic, comments, imports) | Structural changes to the DAG graph |
| **Scope** | Your code repository | Airflow's metadata database |
| **Rollback** | Checkout old commit, redeploy | Trigger run against stored version |
| **Historical runs** | Not linked to specific commit | Permanently linked to version snapshot |
| **Requires deployment** | Yes | No — versions are created at parse time |

The practical answer: use Git to manage and review your DAG source code. Airflow DAG Versioning gives you **runtime audit trail** — knowing exactly what the DAG looked like when each historical run was executed, even if your Git history is messy or someone pushed directly.

They complement each other rather than replacing each other.

---

## Q6: How do you view version history in the Airflow UI?

In the Airflow 3 React UI:

1. Navigate to **DAGs** in the top menu
2. Click on your DAG name to open the DAG detail page
3. Look for the **Versions** tab (alongside Grid, Graph, Code, etc.)
4. The versions list shows:
   - Version number (1, 2, 3...)
   - Creation timestamp
   - A summary of what changed (tasks added/removed)
5. Click any version to see its serialized task graph rendered as a visual graph

You can also compare two versions side by side to see exactly what changed structurally between them.

---

## Q7: What happens to currently running DAG runs when you deploy a new version?

**In-flight runs are not affected.** A DAG run that started on version 5 will complete using version 5's task graph, even if you deploy version 6 while it is still running.

Airflow resolves the task graph for a running `DagRun` from its stored `version_number`, not from the live file system. This means:
- Workers executing tasks read the serialized DAG from the database, not from disk
- Deploying a new DAG file mid-run is safe — it creates version 6 for future runs, but does not alter the in-progress version 5 run
- You cannot accidentally break a running run by pushing a bad update

This is a significant improvement over Airflow 2, where re-parsing a DAG during an active run could cause inconsistencies.

---

## Q8: How does DAG Versioning interact with DAG Bundles?

**DAG Bundles** are a related Airflow 3 concept — a bundle is a configured source of DAG files (a local directory, a Git repo, an S3 path). The DAG Processor knows which bundle each DAG came from.

DAG Versioning and Bundles work together:
- Each version record stores the **bundle name and commit/version reference** that was active when the version was created
- This gives you traceability from a DAG run → DAG version → bundle commit
- If your bundle is a Git repo, you get an exact commit SHA stored against each version

```bash
# Example output of airflow dags versions list
dag_id         version  bundle             created_at
my_pipeline    1        git@main:abc123    2026-01-10 09:00:00
my_pipeline    2        git@main:def456    2026-02-01 14:32:00
my_pipeline    3        git@main:ghi789    2026-03-15 11:05:00
```

This creates a complete audit chain without requiring you to manually correlate deployment timestamps with Git history.

---

## Q9: Are there any limitations or gotchas with DAG Versioning?

Yes, there are a few important ones:

**Storage growth:** Every structural change creates a new serialized snapshot stored in the database. For DAGs that change frequently, this can grow the `dag_version` table significantly. Configure a retention policy using:
```bash
airflow db clean --dag-id my_pipeline --keep-last-n-versions 50
```

**Logic changes are invisible:** Versioning only captures structure, not the Python callable logic. If you change what `my_python_function()` does but keep the task structure the same, no new version is created and you cannot roll back to the old logic via Airflow alone — that requires Git.

**Version numbers are per-DAG, not global:** Version 3 of `pipeline_a` and Version 3 of `pipeline_b` are completely unrelated numbers.

**Backfills use current version by default:** When you trigger a historical backfill, it uses the current version unless you explicitly specify an older version.

---

## Q10: How do you configure how many DAG versions are retained?

By default, Airflow keeps all versions. For long-lived DAGs with frequent changes, you should configure retention.

```ini
# airflow.cfg
[core]
max_dag_versions = 50    # Keep only the last 50 versions per DAG
```

Or clean up manually:
```bash
# Remove old versions, keep the last 20 per DAG
airflow db clean --keep-last-n-dag-versions 20

# Remove all versions for a specific DAG except the current one
airflow dags versions prune --dag-id my_pipeline --keep-last 5
```

The current version (the one associated with any pending or running DagRuns) is **never deleted**, regardless of retention settings.

---

## Q11: How does the Scheduler use DAG versions to schedule new runs?

When the Scheduler evaluates whether to create a new `DagRun`:

1. It queries the database for the **latest version** of each active DAG
2. It reads the schedule, catchup settings, and other scheduling parameters from that latest version's serialized snapshot
3. If a new run is needed, it creates a `DagRun` record and **stamps it with the current version number**
4. The Worker, when it picks up tasks from that run, fetches the serialized DAG for that specific version to build its task context

The Scheduler never reads DAG files directly — it only reads serialized versions from the database, placed there by the DAG Processor. This is the fundamental architecture change that makes versioning possible.

---

## 📂 Navigation
⬅️ **Prev: [Cheatsheet](./Cheatsheet.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next: [New Auth Manager](../33_New_Auth_Manager/Theory.md)**
