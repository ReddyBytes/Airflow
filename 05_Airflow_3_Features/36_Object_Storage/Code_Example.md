# Object Storage — Code Examples

## Navigation
⬅️ **Prev: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## Example 1: Read from S3 Using ObjectStoragePath

A full DAG that reads multiple files from S3, processes them with Pandas, and writes aggregated output. Demonstrates path navigation, existence checks, iteration, and reading.

```python
# dags/s3_reader_example.py
from airflow import DAG
from airflow.decorators import task
from airflow.io.path import ObjectStoragePath
from datetime import datetime

with DAG(
    dag_id="s3_reader_example",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["object-storage", "s3"],
) as dag:

    @task
    def list_input_files(**context) -> list[str]:
        """List all parquet files in today's S3 partition."""
        ds = context["ds"]   # "2024-03-15"

        # Base directory for today's data
        base_path = ObjectStoragePath(
            f"s3://data-lake/raw/transactions/date={ds}/",
            conn_id="aws_default",
        )

        if not base_path.exists():
            print(f"No data directory for {ds}")
            return []

        # List all .parquet files
        parquet_files = [
            str(f)
            for f in base_path.iterdir()
            if f.suffix == ".parquet" and not f.name.startswith("_")
        ]

        print(f"Found {len(parquet_files)} parquet files in {base_path}")
        for f in parquet_files:
            print(f"  - {f}")

        return parquet_files

    @task
    def read_and_validate(file_paths: list[str]) -> dict:
        """Read all files and validate schema."""
        import pandas as pd
        import io

        if not file_paths:
            return {"total_rows": 0, "files_processed": 0, "status": "no_data"}

        all_dfs = []
        required_columns = {"transaction_id", "amount", "currency", "timestamp", "merchant_id"}

        for file_path in file_paths:
            path = ObjectStoragePath(file_path, conn_id="aws_default")

            # Check file size before reading
            stat = path.stat()
            file_size_mb = stat.st_size / (1024 * 1024)
            print(f"Reading {path.name} ({file_size_mb:.2f} MB)")

            if stat.st_size == 0:
                print(f"Skipping empty file: {path.name}")
                continue

            # Read parquet
            content = path.read_bytes()
            df = pd.read_parquet(io.BytesIO(content))

            # Validate schema
            missing_cols = required_columns - set(df.columns)
            if missing_cols:
                raise ValueError(
                    f"Schema mismatch in {path.name}. Missing: {missing_cols}"
                )

            all_dfs.append(df)

        if not all_dfs:
            return {"total_rows": 0, "files_processed": 0, "status": "all_empty"}

        combined = pd.concat(all_dfs, ignore_index=True)
        print(f"Total rows across all files: {len(combined)}")

        return {
            "total_rows": len(combined),
            "files_processed": len(all_dfs),
            "status": "success",
            "columns": list(combined.columns),
            "amount_sum": float(combined["amount"].sum()),
            "unique_merchants": int(combined["merchant_id"].nunique()),
        }

    @task
    def write_daily_summary(validation_result: dict, **context) -> str:
        """Write summary statistics back to S3."""
        import json

        ds = context["ds"]

        if validation_result["status"] != "success":
            print(f"No data to summarize. Status: {validation_result['status']}")
            return ""

        output_path = ObjectStoragePath(
            f"s3://data-lake/summaries/date={ds}/daily_summary.json",
            conn_id="aws_default",
        )

        # Create parent directory if needed
        output_path.parent.mkdir(exist_ok=True, parents=True)

        # Write summary
        summary = {
            "date": ds,
            "processed_at": datetime.utcnow().isoformat(),
            **validation_result,
        }
        output_path.write_text(json.dumps(summary, indent=2))

        print(f"Summary written to: {output_path}")
        print(f"Total volume: ${validation_result['amount_sum']:,.2f}")

        return str(output_path)

    files = list_input_files()
    validation = read_and_validate(files)
    write_daily_summary(validation)
```

---

## Example 2: Write to GCS

A DAG that generates reports and writes them to Google Cloud Storage in multiple formats. Demonstrates writing text, bytes, and using path composition.

```python
# dags/gcs_writer_example.py
from airflow import DAG
from airflow.decorators import task
from airflow.io.path import ObjectStoragePath
from datetime import datetime

with DAG(
    dag_id="gcs_writer_example",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["object-storage", "gcs"],
) as dag:

    @task
    def generate_reports(**context) -> dict:
        """Generate sales reports as different formats."""
        import pandas as pd
        import json
        import io

        ds = context["ds"]

        # Simulated report data
        df = pd.DataFrame({
            "region": ["APAC", "EMEA", "Americas", "ANZ"],
            "revenue": [1_250_000, 980_000, 2_100_000, 340_000],
            "transactions": [45200, 38900, 78500, 12800],
            "avg_order_value": [27.65, 25.19, 26.75, 26.56],
        })

        # GCS base path for today
        gcs_base = ObjectStoragePath(
            f"gs://reports-bucket/daily/{ds}/",
            conn_id="google_cloud_default",
        )

        # Ensure directory exists
        gcs_base.mkdir(exist_ok=True, parents=True)

        results = {}

        # 1. Write CSV report
        csv_path = gcs_base / "regional_sales.csv"
        csv_content = df.to_csv(index=False)
        csv_path.write_text(csv_content, encoding="utf-8")
        print(f"CSV written: {csv_path} ({len(csv_content)} chars)")
        results["csv_path"] = str(csv_path)

        # 2. Write Parquet report
        parquet_path = gcs_base / "regional_sales.parquet"
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False)
        parquet_path.write_bytes(buffer.getvalue())
        print(f"Parquet written: {parquet_path}")
        results["parquet_path"] = str(parquet_path)

        # 3. Write JSON summary
        json_path = gcs_base / "summary.json"
        summary = {
            "date": ds,
            "total_revenue": float(df["revenue"].sum()),
            "total_transactions": int(df["transactions"].sum()),
            "top_region": df.loc[df["revenue"].idxmax(), "region"],
            "regions": df.to_dict("records"),
        }
        json_path.write_text(json.dumps(summary, indent=2))
        print(f"JSON written: {json_path}")
        results["json_path"] = str(json_path)

        # 4. Write HTML dashboard snippet
        html_path = gcs_base / "dashboard.html"
        html_content = df.to_html(
            index=False,
            classes="sales-table",
            border=0,
            float_format="${:,.0f}".format,
        )
        html_path.write_text(f"<html><body>{html_content}</body></html>")
        print(f"HTML written: {html_path}")
        results["html_path"] = str(html_path)

        return results

    @task
    def verify_writes(paths: dict) -> bool:
        """Verify all files were written successfully."""
        all_ok = True

        for format_name, path_str in paths.items():
            path = ObjectStoragePath(path_str, conn_id="google_cloud_default")

            if path.exists():
                size = path.stat().st_size
                print(f"[OK] {format_name}: {path.name} ({size} bytes)")
            else:
                print(f"[FAIL] {format_name}: {path.name} — NOT FOUND")
                all_ok = False

        if not all_ok:
            raise RuntimeError("Some output files are missing — check write operations")

        return all_ok

    @task
    def make_public(paths: dict):
        """Set GCS objects to public-read (for web serving)."""
        # Note: This would use the GCS provider's hook for ACL management
        # ObjectStoragePath handles basic read/write; ACL management
        # still requires the GCS provider hook directly.
        from airflow.providers.google.cloud.hooks.gcs import GCSHook

        hook = GCSHook(gcp_conn_id="google_cloud_default")

        for format_name, path_str in paths.items():
            # Parse gs://bucket/object from path_str
            path_without_scheme = path_str.replace("gs://", "")
            bucket, _, blob = path_without_scheme.partition("/")

            # Make publicly readable
            hook.update_bucket_object_acl(
                bucket_name=bucket,
                object_name=blob,
                acl_entry="allUsers:READER",
            )
            print(f"Made public: {path_str}")

    paths = generate_reports()
    verified = verify_writes(paths)
    make_public(paths)
```

---

## Example 3: Copy Between Backends (S3 → GCS Cross-Cloud Transfer)

A DAG that transfers files from S3 to GCS, demonstrates cross-backend streaming copy, and validates integrity.

```python
# dags/cross_backend_copy.py
from airflow import DAG
from airflow.decorators import task
from airflow.io.path import ObjectStoragePath
from datetime import datetime

with DAG(
    dag_id="s3_to_gcs_transfer",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["object-storage", "cross-cloud", "s3", "gcs"],
) as dag:

    @task
    def list_files_to_transfer(**context) -> list[dict]:
        """List all files in today's S3 partition that need to be transferred."""
        ds = context["ds"]

        source_base = ObjectStoragePath(
            f"s3://source-bucket/exports/{ds}/",
            conn_id="aws_us_east",
        )

        if not source_base.exists():
            print(f"No exports for {ds}")
            return []

        files = []
        for path in source_base.iterdir():
            if path.is_file():
                stat = path.stat()
                files.append({
                    "source_uri": str(path),
                    "filename": path.name,
                    "size_bytes": stat.st_size,
                })
                print(f"  Queued: {path.name} ({stat.st_size:,} bytes)")

        print(f"Total files to transfer: {len(files)}")
        return files

    @task
    def transfer_file(file_info: dict, **context) -> dict:
        """Transfer a single file from S3 to GCS with integrity check."""
        import hashlib
        import shutil

        ds = context["ds"]

        source_path = ObjectStoragePath(
            file_info["source_uri"],
            conn_id="aws_us_east",
        )

        dest_path = ObjectStoragePath(
            f"gs://dest-bucket/imports/{ds}/{file_info['filename']}",
            conn_id="google_cloud_eu",   # Different region/cloud
        )

        print(f"Transferring: {source_path} → {dest_path}")
        print(f"  Size: {file_info['size_bytes']:,} bytes")

        # Create destination directory
        dest_path.parent.mkdir(exist_ok=True, parents=True)

        # For small files (<100MB): read all into memory
        if file_info["size_bytes"] < 100 * 1024 * 1024:
            content = source_path.read_bytes()

            # Compute MD5 before write
            source_md5 = hashlib.md5(content).hexdigest()

            # Write to destination
            dest_path.write_bytes(content)

            # Verify write
            written_content = dest_path.read_bytes()
            dest_md5 = hashlib.md5(written_content).hexdigest()

            if source_md5 != dest_md5:
                raise ValueError(
                    f"Integrity check failed for {file_info['filename']}: "
                    f"source MD5={source_md5}, dest MD5={dest_md5}"
                )

            print(f"  Transfer complete. MD5 verified: {source_md5}")

        else:
            # For large files: stream in chunks to avoid memory issues
            print(f"  Using streaming copy (large file)")
            with source_path.open("rb") as src, dest_path.open("wb") as dst:
                transferred = shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)

        # Verify destination exists and has correct size
        dest_stat = dest_path.stat()
        if dest_stat.st_size != file_info["size_bytes"]:
            raise ValueError(
                f"Size mismatch for {file_info['filename']}: "
                f"expected {file_info['size_bytes']}, got {dest_stat.st_size}"
            )

        return {
            "filename": file_info["filename"],
            "source_uri": str(source_path),
            "dest_uri": str(dest_path),
            "size_bytes": file_info["size_bytes"],
            "status": "success",
        }

    @task
    def generate_transfer_manifest(results: list[dict], **context) -> str:
        """Write a manifest file documenting the completed transfer."""
        import json

        ds = context["ds"]

        successful = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") != "success"]

        manifest = {
            "transfer_date": ds,
            "total_files": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "total_bytes_transferred": sum(r.get("size_bytes", 0) for r in successful),
            "files": results,
        }

        # Write manifest to both source (S3) and destination (GCS)
        manifest_json = json.dumps(manifest, indent=2)

        s3_manifest = ObjectStoragePath(
            f"s3://source-bucket/exports/{ds}/_TRANSFER_MANIFEST.json",
            conn_id="aws_us_east",
        )
        gcs_manifest = ObjectStoragePath(
            f"gs://dest-bucket/imports/{ds}/_TRANSFER_MANIFEST.json",
            conn_id="google_cloud_eu",
        )

        s3_manifest.write_text(manifest_json)
        gcs_manifest.write_text(manifest_json)

        print(f"Transfer complete:")
        print(f"  Files: {len(successful)} succeeded, {len(failed)} failed")
        print(f"  Total bytes: {manifest['total_bytes_transferred']:,}")

        if failed:
            print(f"  Failed files: {[f['filename'] for f in failed]}")
            raise RuntimeError(f"{len(failed)} files failed to transfer")

        return str(gcs_manifest)

    # Use expand() to map transfer_file over each file in parallel
    files = list_files_to_transfer()
    transfer_results = transfer_file.expand(file_info=files)
    generate_transfer_manifest(transfer_results)
```

### Key Patterns in This Example

**Cross-cloud with different conn_ids**: `conn_id="aws_us_east"` for S3 and `conn_id="google_cloud_eu"` for GCS. The code is backend-agnostic — only the connection configuration differs.

**Dynamic task mapping with `expand()`**: `transfer_file.expand(file_info=files)` runs one task instance per file in parallel, using Airflow's native dynamic task mapping.

**Streaming for large files**: `shutil.copyfileobj` with the `ObjectStoragePath.open()` context manager handles arbitrarily large files without loading them entirely into memory.

**Integrity verification**: MD5 hash comparison before and after write catches silent data corruption.

---

## Navigation
⬅️ **Prev: [Event-Driven Scheduling](../35_Event_Driven_Scheduling/Theory.md)** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**
