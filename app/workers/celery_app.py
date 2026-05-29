from celery import Celery

from app.config import get_settings

settings = get_settings()

celery = Celery(
    "devplanet",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.planet_task"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@celery.task(name="devplanet.workers.ping")
def ping() -> str:
    return "pong"
