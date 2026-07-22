from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.workers.capture_task import generate_profile_capture

_FAKE_JPEG = b"\xff\xd8\xff" + b"\x00" * 100  # minimal fake JPEG bytes


def _make_playwright_ctx() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (ctx_manager, browser, page) — ctx is what _launch_playwright() returns."""
    page = MagicMock()
    page.screenshot.return_value = _FAKE_JPEG

    browser = MagicMock()
    browser.new_page.return_value = page

    p = MagicMock()
    p.chromium.launch.return_value = browser

    ctx = MagicMock()
    ctx.__enter__.return_value = p
    ctx.__exit__.return_value = False
    return ctx, browser, page


def _make_s3_mock() -> MagicMock:
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"{}")}
    return s3


def test_capture_task_uploads_jpeg_to_s3() -> None:
    """Task must upload the screenshot as JPEG to the correct S3 key."""
    ctx, _browser, _page = _make_playwright_ctx()
    s3 = _make_s3_mock()

    with (
        patch("app.workers.capture_task._launch_playwright", return_value=ctx),
        patch("app.workers.capture_task.get_s3_client", return_value=s3),
    ):
        result = generate_profile_capture.run("octocat")

    assert result.startswith("ok:")
    assert "octocat.jpg" in result

    s3.put_object.assert_called_once()
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Body"] == _FAKE_JPEG
    assert kwargs["ContentType"] == "image/jpeg"
    assert kwargs["Key"] == "captures/octocat.jpg"
    assert kwargs["ACL"] == "public-read"
    assert kwargs["Bucket"] == "devplanet"


def test_capture_task_navigates_to_capture_url() -> None:
    """Task must navigate to /capture?user=<login> on the configured frontend."""
    ctx, _browser, page = _make_playwright_ctx()
    s3 = _make_s3_mock()

    with (
        patch("app.workers.capture_task._launch_playwright", return_value=ctx),
        patch("app.workers.capture_task.get_s3_client", return_value=s3),
    ):
        generate_profile_capture.run("octocat")

    page.goto.assert_called_once()
    url_arg = page.goto.call_args.args[0]
    assert url_arg.endswith("/capture?user=octocat")
    page.route.assert_not_called()


def test_capture_task_waits_for_planet_ready_signal() -> None:
    ctx, _browser, page = _make_playwright_ctx()
    s3 = _make_s3_mock()

    with (
        patch("app.workers.capture_task._launch_playwright", return_value=ctx),
        patch("app.workers.capture_task.get_s3_client", return_value=s3),
    ):
        generate_profile_capture.run("octocat")

    page.wait_for_function.assert_called_once()
    js_expr = page.wait_for_function.call_args.args[0]
    assert "__PLANET_READY" in js_expr


def test_capture_task_closes_browser_on_error() -> None:
    """Browser must be closed even when wait_for_function raises."""
    ctx, browser, page = _make_playwright_ctx()
    page.wait_for_function.side_effect = TimeoutError("timed out")
    s3 = _make_s3_mock()

    with (
        patch("app.workers.capture_task._launch_playwright", return_value=ctx),
        patch("app.workers.capture_task.get_s3_client", return_value=s3),
        pytest.raises(TimeoutError),
    ):
        generate_profile_capture.run("octocat")

    browser.close.assert_called_once()
