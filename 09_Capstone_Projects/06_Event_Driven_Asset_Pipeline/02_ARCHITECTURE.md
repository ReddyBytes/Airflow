# Architecture — Event-Driven Asset Pipeline

---

## The Problem This Solves

In the old Airflow 2 world, DAGs talked to each other through `ExternalTaskSensor`. The sensor ran on a cron schedule, polled every N seconds, held a worker slot while waiting, and timed out if the upstream DAG ran late. When the upstream DAG finished two hours late because of an API outage, the sensor had already expired and the downstream DAG was marked failed — even though the data eventually arrived and was perfectly valid.

Assets invert the model. Instead of the downstream DAG asking "is the upstream done yet?", the upstream DAG announces "I just produced this data". The downstream DAG wakes up exactly when needed, holds no resources while waiting, and never has to guess at timing.

---

## Full System: Three DAGs, Three Assets

```
01_raw_ingest_orders     [schedule: @daily]
  ingest_orders -------> raw_orders_asset
                              |
                              | (Airflow fires 02 automatically)
                              v
02_transform_orders      [schedule: raw_orders_asset]
  find_latest_partition
  clean_orders
  load_to_warehouse ----> clean_orders_asset
                              |
                              | (Airflow fires 03 automatically)
                              v
03_daily_order_report    [schedule: clean_orders_asset]
  generate_report
  write_report_to_s3 ----> daily_report_asset
```

No `TriggerDagRunOperator`. No polling. No cross-DAG imports. The DAGs are decoupled — each one only knows about the Asset URIs it produces and consumes.

---

## Multi-Asset AND Dependency

When a DAG lists multiple Assets in its schedule, it waits until ALL of them are updated before triggering. This is the AND condition:

```
producer_dag
  segment_b_task --> model_data_asset  ──┐
  segment_c_task --> validation_asset  ──┴──> model_training_dag  [schedule: model_data_asset, validation_asset]
```

If `model_data_asset` is updated but `validation_asset` is not yet, `model_training_dag` waits. Both must arrive — from the same logical run — before the consumer fires. This prevents a training run from pairing yesterday's model data with today's validation holdout.

---

## Asset URI Convention

An Asset URI is a string. It can be any string, but using a real resource URI makes the lineage meaningful:

```
s3://my-data-lake/raw/orders/         <- identifies the S3 prefix that holds raw data
postgres://warehouse/public/orders    <- identifies the Postgres table
s3://my-reports/daily/orders/         <- identifies the S3 prefix for reports
```

Airflow does not read from these URIs. It uses them as keys. Two tasks referencing the same URI string are connected through the same Asset.

The most important rule: define each URI once, in a shared module, and import it everywhere. If DAG 1 writes `Asset("s3://my-data-lake/raw/orders/")` and DAG 2 reads `Asset("s3://my-data-lake/raw/orders ")` (trailing space), they reference different assets and the trigger never fires.

---

## Producer and Consumer Roles

A single DAG can be both a consumer and a producer. `02_transform_orders` is triggered by `raw_orders_asset` (consumer) and emits `clean_orders_asset` (producer). This creates a chain of arbitrary depth.

```
Task role       Code pattern
------------    -----------------------------------------------------
Producer        @task(outlets=[my_asset])  def my_task(): ...
Consumer        with DAG(schedule=[my_asset], ...)
Both            DAG has schedule=[upstream_asset]
                One task in it has outlets=[downstream_asset]
```

---

## Why This Is Better Than ExternalTaskSensor

| Concern | ExternalTaskSensor | Airflow 3 Assets |
|---|---|---|
| Worker slot while waiting | Held the entire wait time | Released immediately |
| Late upstream run | Sensor times out, downstream fails | Consumer fires when data arrives, no timeout |
| Cross-DAG coupling | Consumer imports producer's DAG ID | Consumer references Asset URI only |
| Lineage visibility | Not tracked | Full producer-consumer graph in Assets UI |
| Multi-DAG AND dependency | Complex sensor combinations | `schedule=[asset_a, asset_b]` |

---

## Airflow Connections Required

| Connection ID | Type | Purpose |
|---|---|---|
| `aws_default` | Amazon S3 | Read/write S3 buckets |
| `postgres_warehouse` | Postgres | Read/write warehouse orders table |

---

⬅️ **Prev:** [05 — ML Training Pipeline](../05_ML_Training_Pipeline/01_MISSION.md) &nbsp;&nbsp; ➡️ **Next:** [07 — Stock Price Pipeline](../07_Stock_Price_Pipeline/01_MISSION.md)

**Section:** [09 Capstone Projects](../) &nbsp;&nbsp; **Repo:** [Airflow](../../README.md)
