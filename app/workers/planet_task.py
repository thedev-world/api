from __future__ import annotations

import asyncio
import json

from botocore.exceptions import BotoCoreError, ClientError
from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.clients.s3 import get_s3_client
from app.config import get_settings
from app.domain.planet_snapshot import generate_planet_payload
from app.repositories.planet import PlanetRepository
from app.workers.celery_app import celery

logger = get_task_logger(__name__)


async def _fetch_and_generate(database_url: str) -> bytes:
    """Query the DB and build the compact planet JSON payload."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            entries = await PlanetRepository(db).fetch_planet_entries()
        payload = generate_planet_payload(entries)
        return json.dumps(payload, separators=(",", ":")).encode()
    finally:
        await engine.dispose()


@celery.task(
    name="devplanet.workers.update_planet_json",
    autoretry_for=(BotoCoreError, ClientError),
    max_retries=3,
    default_retry_delay=10,
)
def update_planet_json() -> str:
    """Regenerate planet-data.json and upload it to S3 (full overwrite)."""
    settings = get_settings()

    logger.info("Generating planet-data.json...")
    data = asyncio.run(_fetch_and_generate(settings.database_url))

    logger.info(
        "Uploading %d bytes -> s3://%s/%s",
        len(data),
        settings.s3_bucket_name,
        settings.s3_planet_json_key,
    )
    get_s3_client().put_object(
        Bucket=settings.s3_bucket_name,
        Key=settings.s3_planet_json_key,
        Body=data,
        ACL="public-read",
        ContentType="application/json",
        CacheControl="no-cache, no-store, must-revalidate",
    )

    logger.info("planet-data.json updated successfully.")
    return "ok"
