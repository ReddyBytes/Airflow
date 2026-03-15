# 21 — Testing DAGs: Code Examples

---

## conftest.py — Shared Test Fixtures

```python
# tests/conftest.py
import os
import pytest

# Must be set before any Airflow imports — prevents connection attempts in CI
os.environ.setdefault("AIRFLOW__CORE__UNIT_TEST_MODE", "True")
os.environ.setdefault(
    "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN",
    "sqlite:////tmp/airflow_test.db",
)
os.environ.setdefault("AIRFLOW__CORE__DAGS_FOLDER", "./dags")


@pytest.fixture(scope="session")
def dagbag():
    """
    Load all DAGs once for the entire test session.
    scope="session" means this runs only once — not once per test.
    """
    from airflow.models import DagBag
    bag = DagBag(dag_folder="dags/", include_examples=False)
    return bag


@pytest.fixture(scope="session")
def get_dag(dagbag):
    """
    Helper fixture: returns a function that retrieves a DAG by ID.
    Usage: dag = get_dag("my_etl_pipeline")
    """
    def _get(dag_id: str):
        from airflow.models import DagBag
        dag = dagbag.get_dag(dag_id)
        assert dag is not None, (
            f"DAG '{dag_id}' not found in DagBag. "
            f"Available DAGs: {list(dagbag.dag_ids)}"
        )
        return dag
    return _get
```

---

## test_dag_integrity.py — Import and Structure Tests

```python
# tests/test_dag_integrity.py
"""
DAG integrity tests: verify all DAGs can be imported and meet team standards.
These run fast (no external connections) and should be the first CI check.
"""
import pytest
from airflow.models import DagBag


# ── Import tests ─────────────────────────────────────────────────────────────

def test_no_import_errors(dagbag):
    """Every DAG file must be importable without errors."""
    assert dagbag.import_errors == {}, (
        f"Found {len(dagbag.import_errors)} import error(s):\n"
        + "\n".join(f"  {path}: {err}" for path, err in dagbag.import_errors.items())
    )


def test_dag_count_is_reasonable(dagbag):
    """At least one DAG must exist (catches empty dags/ folder)."""
    assert len(dagbag.dags) > 0, "No DAGs found in dags/ directory"


# ── Convention tests ──────────────────────────────────────────────────────────

def test_all_dags_have_tags(dagbag):
    """Enforce: every DAG must have at least one tag for searchability."""
    violations = [
        dag_id for dag_id, dag in dagbag.dags.items()
        if not dag.tags
    ]
    assert not violations, f"DAGs missing tags: {violations}"


def test_all_dags_have_descriptions(dagbag):
    """Enforce: every DAG must have a description."""
    violations = [
        dag_id for dag_id, dag in dagbag.dags.items()
        if not dag.description
    ]
    assert not violations, f"DAGs missing descriptions: {violations}"


def test_no_dag_uses_catchup_true_with_no_end_date(dagbag):
    """
    DAGs with catchup=True and no end_date can create thousands of runs
    if deployed with a past start_date. Enforce explicit choice.
    """
    risky_dags = [
        dag_id for dag_id, dag in dagbag.dags.items()
        if dag.catchup and dag.end_date is None and dag.schedule is not None
    ]
    # This is a warning test — adjust to assert if your team prohibits it
    if risky_dags:
        import warnings
        warnings.warn(f"DAGs with catchup=True and no end_date: {risky_dags}")


# ── Specific DAG structure tests ──────────────────────────────────────────────

class TestEtlPipelineStructure:
    """Tests for the 'etl_pipeline' DAG."""

    DAG_ID = "etl_pipeline"

    def test_dag_exists(self, dagbag):
        assert self.DAG_ID in dagbag.dag_ids, f"'{self.DAG_ID}' not found"

    def test_task_count(self, get_dag):
        dag = get_dag(self.DAG_ID)
        assert len(dag.tasks) == 5, (
            f"Expected 5 tasks, got {len(dag.tasks)}. "
            f"Tasks: {[t.task_id for t in dag.tasks]}"
        )

    def test_required_task_ids(self, get_dag):
        dag = get_dag(self.DAG_ID)
        task_ids = {t.task_id for t in dag.tasks}
        required = {"extract", "validate", "transform", "load", "notify"}
        missing = required - task_ids
        assert not missing, f"Missing task IDs: {missing}"

    def test_extract_runs_before_transform(self, get_dag):
        dag  = get_dag(self.DAG_ID)
        extract   = dag.get_task("extract")
        transform = dag.get_task("transform")
        downstream_ids = {t.task_id for t in extract.downstream_list}
        assert "transform" in downstream_ids or "validate" in downstream_ids, (
            "extract must be upstream of transform (directly or via validate)"
        )

    def test_load_is_last_before_notify(self, get_dag):
        dag    = get_dag(self.DAG_ID)
        load   = dag.get_task("load")
        notify = dag.get_task("notify")
        downstream_ids = {t.task_id for t in load.downstream_list}
        assert "notify" in downstream_ids

    def test_schedule_is_daily(self, get_dag):
        dag = get_dag(self.DAG_ID)
        assert dag.schedule in ("@daily", "0 0 * * *"), (
            f"Expected daily schedule, got: {dag.schedule}"
        )
```

---

## test_transformations.py — Unit Tests for Python Callables

```python
# tests/test_transformations.py
"""
Unit tests for pure Python transformation functions.
No Airflow, no database, no external connections needed.
"""
import pytest


# ── Functions under test (imported from the DAG module) ───────────────────────
# In a real project, keep callable logic in dags/utils/transformations.py
# and import from there. Here we define them inline for the example.

def normalize_record(record: dict) -> dict:
    """The actual function that would live in dags/utils/transformations.py"""
    return {
        "id":    record["id"],
        "name":  record["name"].strip().title(),
        "email": record["email"].strip().lower(),
        "age":   int(record["age"]),
        "score": round(float(record.get("score", 0)), 2),
    }


def filter_valid_records(records: list[dict]) -> list[dict]:
    """Keep only records with age >= 18 and a non-empty email."""
    return [
        r for r in records
        if r.get("age", 0) >= 18 and r.get("email", "").strip()
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNormalizeRecord:

    def test_name_stripped_and_titled(self):
        result = normalize_record({"id": 1, "name": " alice smith ", "email": "a@b.com", "age": "30"})
        assert result["name"] == "Alice Smith"

    def test_email_lowercased_and_stripped(self):
        result = normalize_record({"id": 1, "name": "Bob", "email": "  BOB@EXAMPLE.COM  ", "age": "25"})
        assert result["email"] == "bob@example.com"

    def test_age_cast_to_int(self):
        result = normalize_record({"id": 1, "name": "Carol", "email": "c@x.com", "age": "42"})
        assert isinstance(result["age"], int)
        assert result["age"] == 42

    def test_score_defaults_to_zero(self):
        result = normalize_record({"id": 1, "name": "Dave", "email": "d@x.com", "age": "20"})
        assert result["score"] == 0.0

    def test_score_rounded_to_two_decimals(self):
        result = normalize_record({"id": 1, "name": "Eve", "email": "e@x.com", "age": "30", "score": "9.9876"})
        assert result["score"] == 9.99

    def test_invalid_age_raises_value_error(self):
        with pytest.raises(ValueError):
            normalize_record({"id": 1, "name": "Frank", "email": "f@x.com", "age": "not-a-number"})


class TestFilterValidRecords:

    def test_underage_records_excluded(self):
        records = [{"age": 17, "email": "a@b.com"}, {"age": 18, "email": "b@b.com"}]
        result  = filter_valid_records(records)
        assert len(result) == 1
        assert result[0]["age"] == 18

    def test_empty_email_excluded(self):
        records = [{"age": 25, "email": ""}, {"age": 30, "email": "valid@x.com"}]
        result  = filter_valid_records(records)
        assert len(result) == 1

    def test_empty_input_returns_empty(self):
        assert filter_valid_records([]) == []

    def test_all_valid_records_pass_through(self):
        records = [
            {"age": 20, "email": "a@x.com"},
            {"age": 35, "email": "b@x.com"},
            {"age": 50, "email": "c@x.com"},
        ]
        result = filter_valid_records(records)
        assert len(result) == 3
```

---

## GitHub Actions Workflow

```yaml
# .github/workflows/dag_tests.yml
name: Airflow DAG Tests

on:
  push:
    branches: ["main", "develop"]
  pull_request:
    branches: ["main"]

jobs:
  test-dags:
    name: Run DAG Tests
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install apache-airflow==3.0.0 pytest pytest-mock

      - name: Initialize Airflow DB (needed for some imports)
        run: airflow db migrate
        env:
          AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: "sqlite:////tmp/airflow_ci.db"
          AIRFLOW__CORE__UNIT_TEST_MODE: "True"

      - name: Run DAG integrity tests
        run: pytest tests/test_dag_integrity.py -v --tb=short
        env:
          AIRFLOW__CORE__UNIT_TEST_MODE: "True"
          AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: "sqlite:////tmp/airflow_ci.db"
          AIRFLOW__CORE__DAGS_FOLDER: "./dags"

      - name: Run transformation unit tests
        run: pytest tests/test_transformations.py -v --tb=short
        # No Airflow env vars needed for pure Python unit tests

      - name: Run full test suite with coverage
        run: pytest tests/ -v --tb=short --cov=dags --cov-report=term-missing
        env:
          AIRFLOW__CORE__UNIT_TEST_MODE: "True"
          AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: "sqlite:////tmp/airflow_ci.db"
```

**What this workflow does on every push and PR:**
1. Sets up Python 3.11.
2. Installs Airflow 3 and pytest.
3. Initializes a throwaway SQLite database (required for some Airflow imports).
4. Runs DAG integrity tests (import errors, structure, conventions).
5. Runs pure Python unit tests (no Airflow env needed).
6. Runs the full suite with coverage reporting.

If any test fails, the workflow fails and the PR cannot be merged (if branch protection is enabled).

---

## Navigation

**Prev:** [20 — Monitoring and Alerting](../20_Monitoring_and_Alerting/Code_Example.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [22 — Custom Timetables](../22_Custom_Timetables/Code_Example.md)
