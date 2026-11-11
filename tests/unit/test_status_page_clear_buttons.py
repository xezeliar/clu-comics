"""The /status page's Clear buttons have to cover every store behind the table.

Three independent stores feed that one table: api.py's ``download_progress``
(the in-process HTTP downloads), ``models.usenet.usenet_downloads`` and
``models.dcpp.dcpp_downloads``. ``/clear_downloads`` only ever knew about the
first, so a finished Usenet or DC++ row survived the button -- DC++ had to be
dismissed a row at a time, and Usenet had no dismiss control at all. Every row
left behind still read "Complete" or "Complete (import pending)", which made
the button look broken.

Text assertions, like test_status_page_cloudflare.py: the wiring lives in
status.html's own JavaScript and there is no Python to exercise.
"""

from pathlib import Path

import pytest

STATUS_HTML = Path(__file__).resolve().parents[2] / "templates" / "status.html"


@pytest.fixture(scope="module")
def status_source():
    return STATUS_HTML.read_text(encoding="utf-8")


class TestClearButtonsCoverClientStores:
    def test_clear_calls_both_stores(self, status_source):
        clear = status_source[status_source.index("      clear: () =>"):]
        clear = clear[:clear.index("}),")]
        assert "dlCall(DL.clear)" in clear
        assert "dlCall(DL.clientClear, 'POST', { bucket: 'finished' })" in clear
        assert "url_for('download_clients.clear_client_downloads')" in status_source

    def test_one_store_failing_does_not_hide_the_other(self, status_source):
        # Each call is already caught, so Promise.all reports both outcomes.
        assert "Some downloads could not be cleared" in status_source

    def test_import_pending_waits_under_needs_attention(self, status_source):
        # Clear ('finished') leaves it alone; Dismiss is the way out.
        assert "job.status === 'complete_no_move'" in status_source
        assert "g: 'attn', err: 'Downloaded, but CLU could not move it" in status_source


class TestBucketNamesMatchTheServer:
    def test_buckets_are_defined_once(self):
        from core.download_utils import (
            CLIENT_CLEAR_BUCKETS,
            CLIENT_COMPLETED_STATUSES,
            CLIENT_FAILED_STATUSES,
        )

        assert set(CLIENT_CLEAR_BUCKETS) == {"completed", "failed", "finished"}
        assert CLIENT_CLEAR_BUCKETS["completed"] is CLIENT_COMPLETED_STATUSES
        assert CLIENT_CLEAR_BUCKETS["failed"] is CLIENT_FAILED_STATUSES
        assert CLIENT_CLEAR_BUCKETS["finished"] == {"complete"}

    def test_import_pending_clears_as_completed_not_failed(self):
        from core.download_utils import (
            CLIENT_COMPLETED_STATUSES,
            CLIENT_FAILED_STATUSES,
        )

        # The status the page renders as "Complete (import pending)".
        assert "complete_no_move" in CLIENT_COMPLETED_STATUSES
        assert "complete_no_move" not in CLIENT_FAILED_STATUSES
        assert CLIENT_COMPLETED_STATUSES.isdisjoint(CLIENT_FAILED_STATUSES)
