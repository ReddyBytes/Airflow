"""
event_driven_pipeline_starter.py
=================================
Scaffold for the Event-Driven Asset Pipeline capstone.

Difficulty: Build Yourself (🔴)
No implementation hints — only the required structure.

Your job:
  1. Create dags/pipeline_assets.py with three Asset definitions
  2. Build the three DAGs below from scratch
  3. Wire them together through Assets (no ExternalTaskSensor, no TriggerDagRunOperator)

This file shows the DAG shells. Fill in every TODO.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# FILE: dags/pipeline_assets.py
# Create this file separately. Define all three assets here and import them
# into each DAG. Using the same object guarantees the URI strings match.
# ─────────────────────────────────────────────────────────────────────────────
#
# from airflow.sdk import Asset
#
# raw_orders_asset   = Asset("s3://my-data-lake/raw/orders/")
# clean_orders_asset = Asset("postgres://warehouse/public/orders")
# daily_report_asset = Asset("s3://my-reports/daily/orders/")


# ─────────────────────────────────────────────────────────────────────────────
# DAG 1 — Raw Ingest (Producer)
# Schedule: @daily (cron-based — entry point of the chain)
# Produces: raw_orders_asset
# ─────────────────────────────────────────────────────────────────────────────

# TODO: implement this DAG
#
# Required tasks:
#   ingest_orders(ds)    — fetch from REST API with pagination, write NDJSON to S3
#                          outlets=[raw_orders_asset]
#   verify_ingest(result) — check S3 key exists after write; raise if missing
#
# API pagination pattern:
#   while True:
#       resp = requests.get(url, params={..., "page": page, "page_size": 500})
#       batch = resp.json().get("data", [])
#       all_orders.extend(batch)
#       if not resp.json().get("has_next_page", False):
#           break
#       page += 1
#
# Write to S3 as NDJSON: "\n".join(json.dumps(row) for row in all_orders)


# ─────────────────────────────────────────────────────────────────────────────
# DAG 2 — Transform Orders (Consumer + Producer)
# Schedule: schedule=[raw_orders_asset]   ← no cron
# Consumes: raw_orders_asset
# Produces: clean_orders_asset
# ─────────────────────────────────────────────────────────────────────────────

# TODO: implement this DAG
#
# Required tasks:
#   find_latest_partition() — list S3 prefixes, return the latest key path
#   clean_orders(s3_key)    — read NDJSON, apply cleaning rules, return JSON string
#   load_to_warehouse(clean_json) — DELETE existing partition, INSERT rows
#                                   outlets=[clean_orders_asset]
#
# Cleaning rules (apply all):
#   - Drop rows where order_id or customer_id is null
#   - Drop rows where amount < 0.01
#   - Normalise order_date to "%Y-%m-%d" string; drop rows where parse fails
#   - Upper-strip the currency column
#   - Round amount to 2 decimal places
#
# Idempotent load:
#   hook.run("DELETE FROM warehouse.orders WHERE order_date = %s", parameters=[order_date])
#   hook.insert_rows(table="warehouse.orders", rows=..., commit_every=500)
#   Confirm: hook.get_first("SELECT COUNT(*) FROM warehouse.orders WHERE order_date = %s")


# ─────────────────────────────────────────────────────────────────────────────
# DAG 3 — Daily Order Report (Consumer)
# Schedule: schedule=[clean_orders_asset]   ← no cron
# Consumes: clean_orders_asset
# Produces: daily_report_asset
# ─────────────────────────────────────────────────────────────────────────────

# TODO: implement this DAG
#
# Required tasks:
#   generate_report() — run the SQL below against the warehouse, return dict
#   write_report_to_s3(report_data) — build an HTML table, upload to S3
#                                     outlets=[daily_report_asset]
#
# Report SQL:
#   SELECT
#       order_date,
#       COUNT(*)                          AS total_orders,
#       ROUND(SUM(amount)::numeric, 2)    AS total_revenue,
#       ROUND(AVG(amount)::numeric, 2)    AS avg_order_value,
#       COUNT(DISTINCT customer_id)       AS unique_customers,
#       SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancellations
#   FROM warehouse.orders
#   WHERE order_date = (SELECT MAX(order_date) FROM warehouse.orders)
#   GROUP BY order_date
#
# S3 key pattern: f"daily/orders/{date}/report.html"
# Bucket: "my-reports"


# ─────────────────────────────────────────────────────────────────────────────
# DAG 4 — Multi-Asset AND Consumer (Extension)
# Schedule: schedule=[asset_a, asset_b]   ← fires only when BOTH are updated
# ─────────────────────────────────────────────────────────────────────────────

# TODO: define two new assets (model_data_asset and validation_asset)
# TODO: add a producer task in another DAG that emits both
# TODO: build this DAG with schedule=[model_data_asset, validation_asset]
# Observe in the UI: if only one asset fires, this DAG waits
