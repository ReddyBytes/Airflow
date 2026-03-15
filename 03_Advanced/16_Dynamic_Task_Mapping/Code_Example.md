# 16 — Dynamic Task Mapping: Code Examples

---

## Example 1: expand() Over a Static List

The simplest use case — process a fixed set of items in parallel.

```python
from airflow import DAG
from airflow.decorators import task
from datetime import datetime
import logging


with DAG(
    dag_id="dynamic_mapping_static_list",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example", "dynamic_mapping"],
) as dag:

    @task
    def process_region(region: str) -> dict:
        logging.info(f"Processing data for region: {region}")
        # Simulate processing
        record_count = {"us-east": 1200, "eu-west": 950, "ap-south": 430}
        return {"region": region, "records": record_count.get(region, 0)}

    @task
    def summarize_all(results: list[dict]) -> None:
        total = sum(r["records"] for r in results)
        logging.info(f"Total records processed across all regions: {total}")
        for r in results:
            logging.info(f"  {r['region']}: {r['records']} records")

    # expand() creates 3 task instances in parallel
    region_results = process_region.expand(
        region=["us-east", "eu-west", "ap-south"]
    )

    # summarize receives a list of all 3 mapped outputs
    summarize_all(region_results)
```

**What happens at runtime:**
- `process_region[0]` runs with `region="us-east"`
- `process_region[1]` runs with `region="eu-west"`
- `process_region[2]` runs with `region="ap-south"`
- All three run in parallel
- `summarize_all` receives `[{"region": "us-east", ...}, {"region": "eu-west", ...}, ...]`

---

## Example 2: expand() Over an XCom Result (Truly Dynamic)

The list is not known at DAG write time — it comes from a real data source at runtime.

```python
from airflow import DAG
from airflow.decorators import task
from datetime import datetime
import logging


with DAG(
    dag_id="dynamic_mapping_from_xcom",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example", "dynamic_mapping"],
) as dag:

    @task
    def discover_files() -> list[str]:
        """
        In production this would query S3, a database, or an API.
        Returns a different list every run depending on what's available.
        """
        import datetime as dt
        today = dt.date.today().isoformat()
        logging.info(f"Scanning for files uploaded on {today}")

        # Simulated — in production: s3_client.list_objects(Bucket=..., Prefix=today)
        files = [
            f"data/{today}/customer_001.csv",
            f"data/{today}/customer_002.csv",
            f"data/{today}/customer_003.csv",
        ]
        logging.info(f"Found {len(files)} files to process")
        return files

    @task
    def validate_file(filepath: str, **context) -> dict:
        idx = context["task_instance"].map_index
        logging.info(f"[Instance #{idx}] Validating: {filepath}")
        # Simulate validation
        return {"filepath": filepath, "valid": True, "rows": 500}

    @task
    def transform_file(validation_result: dict, **context) -> str:
        idx = context["task_instance"].map_index
        filepath = validation_result["filepath"]
        if not validation_result["valid"]:
            raise ValueError(f"File failed validation: {filepath}")
        logging.info(f"[Instance #{idx}] Transforming: {filepath}")
        return filepath.replace("data/", "processed/")

    @task
    def generate_report(processed_files: list[str]) -> None:
        logging.info(f"Pipeline complete. Processed {len(processed_files)} files:")
        for f in processed_files:
            logging.info(f"  {f}")

    # The list comes from a task — count is determined at runtime
    file_list        = discover_files()
    validation_results = validate_file.expand(filepath=file_list)
    processed_paths    = transform_file.expand(validation_result=validation_results)
    generate_report(processed_paths)
```

**Key points:**
- `discover_files()` runs first and returns however many files exist today.
- `validate_file` and `transform_file` are chained — paired 1:1 by `map_index`.
- `map_index` is logged inside each task to show which instance is running.
- `generate_report` collects all results into one list.

---

## Example 3: partial() with expand()

Fix some parameters, vary one across a list.

```python
from airflow import DAG
from airflow.decorators import task
from datetime import datetime
import logging


with DAG(
    dag_id="dynamic_mapping_with_partial",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example", "dynamic_mapping"],
) as dag:

    @task
    def get_tables_to_load() -> list[str]:
        """Returns the list of tables that need to be synced today."""
        return ["orders", "order_items", "customers", "products"]

    @task
    def load_table(
        table_name: str,
        target_schema: str,
        target_database: str,
        truncate_before_load: bool,
        **context,
    ) -> dict:
        idx = context["task_instance"].map_index
        logging.info(
            f"[Instance #{idx}] Loading {target_database}.{target_schema}.{table_name} "
            f"(truncate={truncate_before_load})"
        )
        return {"table": table_name, "rows_loaded": 1000}

    @task
    def send_load_summary(results: list[dict]) -> None:
        total = sum(r["rows_loaded"] for r in results)
        tables = [r["table"] for r in results]
        logging.info(f"Loaded {len(tables)} tables, {total} total rows: {tables}")

    tables = get_tables_to_load()

    # partial() fixes the 3 constants; expand() varies only table_name
    load_results = load_table.partial(
        target_schema="raw",
        target_database="analytics_db",
        truncate_before_load=True,
    ).expand(table_name=tables)

    send_load_summary(load_results)
```

---

## Example 4: Cross-Product expand() with map_index Access

Train models for every combination of algorithm and learning rate.

```python
from airflow import DAG
from airflow.decorators import task
from datetime import datetime
import logging


ALGORITHMS     = ["random_forest", "gradient_boost", "neural_net"]
LEARNING_RATES = [0.001, 0.01, 0.1]
# Cross-product: 3 × 3 = 9 task instances


with DAG(
    dag_id="cross_product_mapping",
    start_date=datetime(2024, 1, 1),
    schedule=None,              # manually triggered
    catchup=False,
    tags=["example", "dynamic_mapping"],
) as dag:

    @task
    def train_model(algorithm: str, learning_rate: float, **context) -> dict:
        idx = context["task_instance"].map_index
        logging.info(
            f"[Instance #{idx}] Training {algorithm} "
            f"with learning_rate={learning_rate}"
        )
        # Simulate training — return mock metrics
        import random
        accuracy = round(0.80 + random.uniform(0, 0.15), 4)
        return {
            "map_index":     idx,
            "algorithm":     algorithm,
            "learning_rate": learning_rate,
            "accuracy":      accuracy,
        }

    @task
    def select_best_model(results: list[dict]) -> dict:
        """Reduce: pick the model with the highest accuracy."""
        best = max(results, key=lambda r: r["accuracy"])
        logging.info(
            f"Best model: {best['algorithm']} "
            f"lr={best['learning_rate']} "
            f"accuracy={best['accuracy']}"
        )
        logging.info("All results:")
        for r in sorted(results, key=lambda x: x["accuracy"], reverse=True):
            logging.info(
                f"  [{r['map_index']:2d}] {r['algorithm']:15s} "
                f"lr={r['learning_rate']:.3f}  acc={r['accuracy']:.4f}"
            )
        return best

    # expand() with two params = Cartesian product
    # map_index 0 → (random_forest, 0.001)
    # map_index 1 → (random_forest, 0.01)
    # map_index 2 → (random_forest, 0.1)
    # map_index 3 → (gradient_boost, 0.001)
    # ... and so on for all 9 combinations
    all_results = train_model.expand(
        algorithm=ALGORITHMS,
        learning_rate=LEARNING_RATES,
    )

    select_best_model(all_results)
```

**What the map_index assignment looks like:**

| map_index | algorithm | learning_rate |
|---|---|---|
| 0 | random_forest | 0.001 |
| 1 | random_forest | 0.01 |
| 2 | random_forest | 0.1 |
| 3 | gradient_boost | 0.001 |
| 4 | gradient_boost | 0.01 |
| 5 | gradient_boost | 0.1 |
| 6 | neural_net | 0.001 |
| 7 | neural_net | 0.01 |
| 8 | neural_net | 0.1 |

All 9 `train_model` instances run in parallel. `select_best_model` runs once after all 9 complete, receiving a list of 9 result dicts.

---

## Navigation

**Prev:** [15 — Task Groups](../15_Task_Groups/Code_Example.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [17 — Deferrable Operators](../17_Deferrable_Operators/Code_Example.md)
