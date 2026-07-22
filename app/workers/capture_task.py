from __future__ import annotations

from celery.utils.log import get_task_logger

from app.clients.s3 import get_s3_client
from app.config import get_settings
from app.workers.celery_app import celery

logger = get_task_logger(__name__)


def _launch_playwright():
    """Lazy Playwright entrypoint.

    Kept as a small indirection so the module stays importable in environments
    where Playwright is not installed (e.g. the API image, unit tests) and so
    tests can mock this single hook instead of the whole playwright package.
    """
    from playwright.sync_api import sync_playwright

    return sync_playwright()


@celery.task(
    name="devplanet.workers.generate_profile_capture",
    max_retries=2,
    default_retry_delay=15,
)
def generate_profile_capture(github_login: str) -> str:
    """Capture /capture?user=<login> with Playwright and upload the image to S3."""
    settings = get_settings()
    url = f"{settings.frontend_internal_url}/capture?user={github_login}"
    key = f"{settings.s3_capture_key_prefix}{github_login}.jpg"

    logger.info("Capturing profile for %r -> %s", github_login, url)

    with _launch_playwright() as p:
        browser = p.chromium.launch(
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                # Enable software WebGL
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--disable-gpu-sandbox",
            ]
        )
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 630})
            page.on("console", lambda msg: logger.info("browser[%s]: %s", msg.type, msg.text))
            page.on("pageerror", lambda err: logger.error("browser pageerror: %s", err))
            page.on(
                "requestfailed",
                lambda req: logger.error("browser requestfailed: %s %s", req.url, req.failure),
            )
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_function("() => window.__PLANET_READY === true", timeout=30_000)
            screenshot = page.screenshot(type="jpeg", quality=85)
        finally:
            browser.close()

    logger.info("Uploading %d bytes -> s3://%s/%s", len(screenshot), settings.s3_bucket_name, key)
    get_s3_client().put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=screenshot,
        ACL="public-read",
        ContentType="image/jpeg",
        CacheControl="public, max-age=3600",
    )

    logger.info("Profile capture done for %r.", github_login)
    return f"ok: s3://{settings.s3_bucket_name}/{key}"
