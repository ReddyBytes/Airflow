# 17 — Deferrable Operators: Cheatsheet

## Deferrable vs Non-Deferrable

| Aspect | Non-deferrable | Deferrable |
|---|---|---|
| Worker during wait | Occupied (blocked) | Released (free) |
| Wait mechanism | Polling loop with `time.sleep()` | Async coroutine in Triggerer |
| Worker slots needed for 100 sensors | 100 | ~0 (just a Trigger object) |
| Required extra component | None | Triggerer process must be running |
| Performance overhead | High (scales with waiting tasks) | Low (one Triggerer handles thousands) |
| Code complexity | Simple | Slightly more complex |

---

## Common Deferrable Sensors

| Use case | Deferrable class | Import |
|---|---|---|
| Wait N minutes/seconds | `TimeDeltaSensorAsync` | `airflow.sensors.time_delta` |
| Wait until datetime | `DateTimeSensorAsync` | `airflow.sensors.date_time` |
| Wait for another DAG task | `ExternalTaskSensorAsync` | `airflow.sensors.external_task` |
| Wait for S3 file | `S3KeySensorAsync` | `airflow.providers.amazon.aws.sensors.s3` |
| Wait for GCS object | `GCSObjectExistenceSensorAsync` | `airflow.providers.google.cloud.sensors.gcs` |
| Wait for HTTP endpoint | `HttpSensorAsync` | `airflow.providers.http.sensors.http` |

---

## self.defer() Syntax

```python
# Inside operator's execute() method:
self.defer(
    trigger=MyTrigger(param1=value1),    # Trigger instance
    method_name="execute_complete",       # Method to call when trigger fires
    kwargs={},                            # Optional extra kwargs for the resume method
    timeout=timedelta(hours=2),           # Optional: fail if trigger doesn't fire in time
)
```

---

## BaseTrigger Implementation Skeleton

```python
import asyncio
from airflow.triggers.base import BaseTrigger, TriggerEvent


class MyTrigger(BaseTrigger):

    def __init__(self, resource_id: str, poll_interval: int = 30):
        super().__init__()
        self.resource_id  = resource_id
        self.poll_interval = poll_interval

    def serialize(self) -> tuple[str, dict]:
        # Must return importable path + __init__ kwargs
        return (
            "my_package.triggers.MyTrigger",
            {"resource_id": self.resource_id, "poll_interval": self.poll_interval},
        )

    async def run(self):
        while True:
            status = await self._async_check_status(self.resource_id)
            if status == "COMPLETE":
                yield TriggerEvent({"status": status, "resource_id": self.resource_id})
                return
            await asyncio.sleep(self.poll_interval)

    async def _async_check_status(self, resource_id: str) -> str:
        # Use aiohttp, aiobotocore, or any async library here
        # DO NOT use requests (blocking) — it defeats the purpose
        ...
```

---

## Deferrable Operator Skeleton

```python
from datetime import timedelta
from airflow.models import BaseOperator
from my_package.triggers import MyTrigger


class MyDeferrableOperator(BaseOperator):

    def __init__(self, resource_id: str, **kwargs):
        super().__init__(**kwargs)
        self.resource_id = resource_id

    def execute(self, context):
        # Kick off the work, then defer
        self.log.info(f"Starting {self.resource_id}, deferring...")
        self.defer(
            trigger=MyTrigger(resource_id=self.resource_id),
            method_name="execute_complete",
            timeout=timedelta(hours=4),
        )

    def execute_complete(self, context, event: dict):
        # Called by Airflow when the trigger yields TriggerEvent
        self.log.info(f"Resumed: {event}")
        return event.get("resource_id")
```

---

## Starting the Triggerer

```bash
# Standalone
airflow triggerer

# Docker Compose — add as a service:
# airflow-triggerer:
#   command: triggerer
#   ...same image and volumes as scheduler...
```

---

## Navigation

**Prev:** [16 — Dynamic Task Mapping](../16_Dynamic_Task_Mapping/Cheatsheet.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [18 — Callbacks and SLAs](../18_Callbacks_and_SLAs/Cheatsheet.md)
