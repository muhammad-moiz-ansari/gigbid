import asyncio

from celery import Celery

from apps.api.config import settings
from worker.runtime import drain_once, process_run

app = Celery("gigbid", broker=settings().redis_url)
app.conf.update(task_acks_late=True, task_reject_on_worker_lost=True,
                worker_prefetch_multiplier=1, broker_connection_retry_on_startup=True,
                beat_schedule={"recover-durable-outbox": {"task": "worker.recover", "schedule": 30.0},
                               "saved-searches": {"task": "worker.scout", "schedule": 60.0},
                               "marketplace-events": {"task": "worker.sync", "schedule": 60.0},
                               "mock-outcomes": {"task": "worker.mock_outcomes", "schedule": 60.0},
                               "upwork-retention": {"task": "worker.retention", "schedule": 3600.0}})


@app.task(name="worker.execute", soft_time_limit=240, time_limit=270)
def execute_run(run_id):
    asyncio.run(process_run(run_id))


@app.task(name="worker.recover")
def recover():
    asyncio.run(drain_once())


@app.task(name="worker.scout")
def scout():
    from worker.scout import scout_all
    asyncio.run(scout_all())


@app.task(name="worker.sync")
def sync():
    from worker.pipeline import sync_all
    asyncio.run(sync_all())


@app.task(name="worker.retention")
def retention():
    from worker.retention import purge_all
    asyncio.run(purge_all())


@app.task(name="worker.mock_outcomes")
def mock_outcomes():
    from worker.pipeline import tick_all
    tick_all()
