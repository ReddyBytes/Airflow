# 17 — Deferrable Operators: Interview Q&A

---

**Q1. What are deferrable operators and why were they introduced?**

Deferrable operators are Airflow operators that can release their worker slot while waiting for an external event, instead of occupying the slot in a blocking polling loop. They were introduced to solve the scalability problem with sensors: a traditional sensor holds a worker slot for its entire lifetime — which could be hours — doing nothing but sleeping between polls. With deferrable operators, the task enters a `DEFERRED` state and a lightweight async Trigger object watches for the event inside the Triggerer process. Workers are free to run real work.

---

**Q2. What is the Triggerer and how is it different from the Scheduler?**

The Triggerer is a dedicated Airflow process (run with `airflow triggerer`) that manages all deferred tasks. It runs a single asyncio event loop that executes all active Trigger objects as concurrent async coroutines — one process can handle thousands of triggers simultaneously without blocking. The Scheduler is responsible for parsing DAGs, determining which tasks are ready to run, and placing them on the queue. The Triggerer's only job is to watch for trigger conditions and notify the scheduler when they fire.

---

**Q3. How does self.defer() work at a code level?**

You call `self.defer()` inside an operator's `execute()` method. It takes a `trigger` argument (a `BaseTrigger` instance) and a `method_name` argument (the name of the method to call when the trigger fires). Calling `self.defer()` raises an internal `TaskDeferred` exception that Airflow catches — it marks the task as `DEFERRED`, stores the serialized trigger in the database, and releases the worker. When the trigger fires, Airflow calls the named method (e.g., `execute_complete`) on the operator to resume execution.

---

**Q4. What is a BaseTrigger and what methods does it require?**

`BaseTrigger` is the base class for all Trigger objects. Subclasses must implement two methods:

- `serialize()` — returns a `(class_path, kwargs_dict)` tuple so the trigger can be re-instantiated after a Triggerer restart.
- `run()` — an async generator that monitors the condition and `yield`s a `TriggerEvent` when it fires.

The `run()` method must be truly async — it should use `asyncio.sleep()` and async I/O libraries (like `aiohttp` or `aiobotocore`), never blocking calls like `requests` or `time.sleep()`.

---

**Q5. When should you use a deferrable operator instead of a regular sensor?**

Use a deferrable operator any time a task spends significant time waiting for something external:
- Waiting for a file to arrive (S3, GCS, SFTP)
- Waiting for a long-running job to finish (Dataproc, EMR, Spark)
- Waiting for a time delay of more than a few seconds
- Polling an HTTP endpoint until a job completes

The rule of thumb: if the wait time is more than a minute and you have multiple such sensors, go deferrable. If you only have one or two sensors waiting a few seconds, the added complexity may not be worth it.

---

**Q6. How many workers do you need with deferrable sensors compared to traditional sensors?**

With traditional sensors, you need one worker slot per waiting sensor. If you have 50 sensors waiting overnight, you need 50 workers occupied doing nothing. With deferrable sensors, the deferred tasks consume no worker slots — they live only as Trigger objects inside the Triggerer's event loop. You need zero workers for the waiting period. Workers are only needed briefly at task start (to call `self.defer()`) and at task completion (to call `execute_complete()`).

---

**Q7. What happens to deferred tasks if the Triggerer process crashes?**

Deferred tasks transition back to a scheduled/queued state so they can be restarted. The Trigger's `serialize()` method exists precisely for this reason — the trigger can be re-instantiated from the serialized data stored in the metadata database. For high availability, you can run multiple Triggerer instances; Airflow distributes triggers across them.

---

**Q8. What is the difference between deferring and using poke_interval on a regular sensor?**

Both involve waiting, but the mechanism is fundamentally different. A regular sensor with `poke_interval=30` still holds a worker slot the entire time — it just sleeps for 30 seconds between checks. The worker is blocked and unavailable for other tasks. A deferrable sensor releases the worker slot entirely during the wait. `poke_interval` is a setting on traditional sensors that controls how often they check; it does not free the worker.

---

**Q9. Can you use deferrable operators with any Executor?**

The Triggerer process works independently of the executor. However, deferrable operators only make a meaningful difference when you have a limited pool of workers — which is the case with CeleryExecutor and KubernetesExecutor. With LocalExecutor (all tasks run on the scheduler machine), the benefit is less significant since workers and the scheduler share the same machine. In all cases, you still need the Triggerer process running, or deferred tasks will stay in `DEFERRED` state indefinitely.

---

**Q10. How do you convert an existing sensor to use deferral?**

1. Create a `BaseTrigger` subclass with the async polling logic in `run()`.
2. Change the operator's `execute()` to call `self.defer(trigger=..., method_name="execute_complete")` instead of looping.
3. Add an `execute_complete(self, context, event)` method that handles the result when the trigger fires.
4. Ensure the Triggerer process is running in your deployment.

For standard Airflow sensors, just swap the class name: `S3KeySensor` → `S3KeySensorAsync`, `TimeDeltaSensor` → `TimeDeltaSensorAsync`. The interface (parameters) stays the same.

---

## Navigation

**Prev:** [16 — Dynamic Task Mapping](../16_Dynamic_Task_Mapping/Interview_QA.md) | **Home:** [Learning Path](../../00_Learning_Guide/Learning_Path.md) | **Next:** [18 — Callbacks and SLAs](../18_Callbacks_and_SLAs/Interview_QA.md)
