"""Tests for HttpTransport — mocks urllib to avoid network calls."""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from agentweave.transport.http import (
    HUB_MAX_RESPONSE_BODY,
    HttpTransport,
    HubTransportError,
)


def _make_response(data, status=200):
    """Return a context-manager mock that behaves like urllib.urlopen."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode()
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code, body=b"", headers=None):
    import urllib.error

    return urllib.error.HTTPError(
        url="http://test/api/v1/x",
        code=code,
        msg={
            200: "OK",
            429: "Too Many Requests",
            500: "Internal Server Error",
            502: "Bad Gateway",
        }.get(code, "Error"),
        hdrs=headers or {},
        fp=io.BytesIO(body),
    )


class TestHttpTransport(unittest.TestCase):
    def setUp(self):
        self.transport = HttpTransport(
            url="http://localhost:8000",
            api_key="aw_live_testkey",
            project_id="proj-test",
        )

    @patch("urllib.request.urlopen")
    def test_send_message_success(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({"id": "msg-abc"})
        result = self.transport.send_message(
            {
                "id": "msg-abc",
                "from": "claude",
                "to": "kimi",
                "subject": "Hi",
                "content": "Hello",
            }
        )
        self.assertTrue(result)
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_send_message_failure(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        result = self.transport.send_message({"from": "claude", "to": "kimi", "content": "Hi"})
        self.assertFalse(result)

    @patch("urllib.request.urlopen")
    def test_get_pending_messages(self, mock_urlopen):
        messages = [{"id": "msg-1", "from": "claude", "to": "kimi"}]
        mock_urlopen.return_value = _make_response(messages)
        result = self.transport.get_pending_messages("kimi")
        self.assertEqual(result, messages)

    @patch("urllib.request.urlopen")
    def test_get_pending_messages_failure(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("timeout")
        result = self.transport.get_pending_messages("kimi")
        self.assertEqual(result, [])

    @patch("urllib.request.urlopen")
    def test_archive_message(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({"success": True})
        result = self.transport.archive_message("msg-abc")
        self.assertTrue(result)

    @patch("urllib.request.urlopen")
    def test_send_task(self, mock_urlopen):
        mock_urlopen.return_value = _make_response({"id": "task-abc"})
        result = self.transport.send_task(
            {
                "id": "task-abc",
                "title": "Build feature",
                "assignee": "kimi",
            }
        )
        self.assertTrue(result)

    @patch("urllib.request.urlopen")
    def test_get_active_tasks(self, mock_urlopen):
        tasks = [{"id": "task-1", "assignee": "kimi", "status": "pending"}]
        mock_urlopen.return_value = _make_response(tasks)
        result = self.transport.get_active_tasks("kimi")
        self.assertEqual(result, tasks)

    @patch("urllib.request.urlopen")
    def test_get_active_tasks_all(self, mock_urlopen):
        tasks = [{"id": "task-1"}, {"id": "task-2"}]
        mock_urlopen.return_value = _make_response(tasks)
        result = self.transport.get_active_tasks()
        self.assertEqual(result, tasks)

    def test_get_transport_type(self):
        self.assertEqual(self.transport.get_transport_type(), "http")


class TestHttpTransportRetry(unittest.TestCase):
    """H3: HttpTransport must retry 5xx, 429, and URLError with backoff.

    Was: no retry — first failure returned False. Spec calls for honoring
    Retry-After header on 429. We use Retry-After: 0 in the tests to keep
    the suite fast.
    """

    def setUp(self):
        self.transport = HttpTransport(
            url="http://localhost:8000",
            api_key="aw_live_testkey",
            project_id="proj-test",
        )

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_send_message_retries_on_500_then_succeeds(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _http_error(500),
            _http_error(500),
            _make_response({"id": "msg-1"}),
        ]
        result = self.transport.send_message(
            {"id": "msg-1", "from": "claude", "to": "kimi", "content": "x", "subject": ""}
        )
        self.assertTrue(result)
        self.assertEqual(mock_urlopen.call_count, 3)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_send_message_gives_up_after_max_retries(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        result = self.transport.send_message(
            {"id": "msg-1", "from": "claude", "to": "kimi", "content": "x", "subject": ""}
        )
        self.assertFalse(result)
        # Default max attempts: 1 initial + N retries
        self.assertGreaterEqual(mock_urlopen.call_count, 2)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_send_message_does_not_retry_on_4xx_other_than_429(self, mock_urlopen):
        """A 400 (bad request) must NOT be retried — caller error, transient retry is pointless."""
        mock_urlopen.side_effect = [_http_error(400, b"bad")]
        result = self.transport.send_message(
            {"id": "msg-1", "from": "claude", "to": "kimi", "content": "x", "subject": ""}
        )
        self.assertFalse(result)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_send_message_retries_on_429_and_succeeds(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _http_error(429, b"slow down", headers={"Retry-After": "0"}),
            _make_response({"id": "msg-1"}),
        ]
        result = self.transport.send_message(
            {"id": "msg-1", "from": "claude", "to": "kimi", "content": "x", "subject": ""}
        )
        self.assertTrue(result)
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_send_message_retries_on_url_error_then_succeeds(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = [
            urllib.error.URLError("Connection refused"),
            _make_response({"id": "msg-1"}),
        ]
        result = self.transport.send_message(
            {"id": "msg-1", "from": "claude", "to": "kimi", "content": "x", "subject": ""}
        )
        self.assertTrue(result)
        self.assertEqual(mock_urlopen.call_count, 2)


class TestHttpTransportInvalidResponse(unittest.TestCase):
    """H6: 2xx response with a non-JSON body must NOT crash with
    JSONDecodeError; it must raise HubTransportError with classification
    'hub_invalid_response'.
    """

    def setUp(self):
        self.transport = HttpTransport(
            url="http://localhost:8000",
            api_key="aw_live_testkey",
            project_id="proj-test",
        )

    @patch("urllib.request.urlopen")
    def test_html_response_classified_as_invalid(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b"<html><body>502 Bad Gateway</body></html>"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        with self.assertRaises(HubTransportError) as ctx:
            self.transport._request("GET", "/agents")
        self.assertEqual(ctx.exception.classification, "hub_invalid_response")
        self.assertIsNone(ctx.exception.status_code)

    @patch("urllib.request.urlopen")
    def test_empty_response_returns_empty_dict(self, mock_urlopen):
        """A 2xx with an empty body is treated as 'no content' and returns
        an empty dict. This is a common case for DELETE-style endpoints
        and shouldn't be misclassified as an error.
        """
        resp = MagicMock()
        resp.read.return_value = b""
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = self.transport._request("GET", "/agents")
        self.assertEqual(result, {})

    @patch("urllib.request.urlopen")
    def test_plain_text_response_classified_as_invalid(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b"OK"  # not JSON
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        with self.assertRaises(HubTransportError) as ctx:
            self.transport._request("GET", "/agents")
        self.assertEqual(ctx.exception.classification, "hub_invalid_response")


class TestHttpTransportResponseSizeCap(unittest.TestCase):
    """S10: HttpTransport must cap response body size to prevent OOM
    on a misbehaving Hub. Responses over the cap raise
    HubTransportError('hub_response_too_large'). The cap is 10 MB.
    """

    def setUp(self):
        self.transport = HttpTransport(
            url="http://localhost:8000",
            api_key="aw_live_testkey",
            project_id="proj-test",
        )

    @patch("urllib.request.urlopen")
    def test_response_body_over_cap_raises(self, mock_urlopen):
        """A response 1 byte over the cap must raise."""
        # 1 byte over the cap
        huge = b"x" * (HUB_MAX_RESPONSE_BODY + 1)
        resp = MagicMock()
        resp.read.return_value = huge
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        with self.assertRaises(HubTransportError) as ctx:
            self.transport._request("GET", "/messages")
        self.assertEqual(ctx.exception.classification, "hub_response_too_large")

    @patch("urllib.request.urlopen")
    def test_response_body_at_cap_is_accepted(self, mock_urlopen):
        """A response at exactly the cap is accepted (no overflow)."""
        # A small but valid JSON, well under the cap
        resp = MagicMock()
        resp.read.return_value = json.dumps({"id": "msg-x"}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        result = self.transport._request("GET", "/messages")
        self.assertEqual(result, {"id": "msg-x"})

    def test_response_body_cap_constant_is_10mb(self):
        """Sanity: the cap must be 10 MB (10 * 1024 * 1024 = 10485760)."""
        self.assertEqual(HUB_MAX_RESPONSE_BODY, 10 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# PR 12 — classification coverage
#
# The existing tests cover the retry loop and the response body cap;
# they don't pin down which HTTPError code maps to which classification.
# These 8 tests lock the mapping so a future refactor of _request can't
# silently swap, say, 401 and 404.
# ---------------------------------------------------------------------------


class TestHttpTransportErrorClassification(unittest.TestCase):
    """HubTransportError.classification values for every HTTPError branch."""

    def setUp(self):
        self.transport = HttpTransport(
            url="http://localhost:8000",
            api_key="aw_live_testkey",
            project_id="proj-test",
        )

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_http_401_classified_as_hub_auth_failed(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(401, b"unauthorized")
        with self.assertRaises(HubTransportError) as ctx:
            self.transport._request("GET", "/agents")
        self.assertEqual(ctx.exception.classification, "hub_auth_failed")
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_http_403_classified_as_hub_auth_failed(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(403, b"forbidden")
        with self.assertRaises(HubTransportError) as ctx:
            self.transport._request("GET", "/agents")
        self.assertEqual(ctx.exception.classification, "hub_auth_failed")
        self.assertEqual(ctx.exception.status_code, 403)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_http_404_classified_as_hub_project_missing(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(404, b"project not found")
        with self.assertRaises(HubTransportError) as ctx:
            self.transport._request("GET", "/agents")
        self.assertEqual(ctx.exception.classification, "hub_project_missing")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_http_408_retries_then_succeeds(self, mock_urlopen):
        """408 Request Timeout is in HUB_RETRY_STATUSES, so the first failure
        should be retried. This pins both the classification AND the retry."""
        mock_urlopen.side_effect = [
            _http_error(408, b"timed out"),
            _make_response({"ok": True}),
        ]
        result = self.transport._request("GET", "/agents")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_http_500_exhausts_retries_with_hub_api_error(self, mock_urlopen):
        """500 is in HUB_RETRY_STATUSES, but max_attempts=3 means we give up
        after 3 calls with classification 'hub_api_error'."""
        mock_urlopen.side_effect = [
            _http_error(500, b"boom 1"),
            _http_error(500, b"boom 2"),
            _http_error(500, b"boom 3"),
        ]
        with self.assertRaises(HubTransportError) as ctx:
            self.transport._request("GET", "/agents")
        self.assertEqual(ctx.exception.classification, "hub_api_error")
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(mock_urlopen.call_count, 3)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_url_error_with_timeout_reason_classified_as_hub_timeout(self, mock_urlopen):
        """A URLError whose .reason is 'timed out' (the real-world case that
        urlopen produces) is classified as 'hub_timeout' and retried."""
        import socket
        import urllib.error

        # Real-world shape: URLError(reason=socket.timeout("...")) — this is
        # what urlopen actually raises on a socket read timeout in Python
        # 3.10+. We pass a real socket.timeout instance as the reason.
        mock_urlopen.side_effect = urllib.error.URLError(socket.timeout("read timed out"))
        # First 2 attempts fail, 3rd succeeds (max_attempts=3).
        mock_urlopen.side_effect = [
            urllib.error.URLError(socket.timeout("read timed out")),
            urllib.error.URLError(socket.timeout("read timed out")),
            _make_response({"ok": True}),
        ]
        result = self.transport._request("GET", "/agents")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 3)

    @patch("agentweave.transport.http.time.sleep", lambda *_: None)
    @patch("urllib.request.urlopen")
    def test_url_error_unrelated_classified_as_hub_unreachable(self, mock_urlopen):
        """A URLError whose .reason doesn't contain 'timed out' should land in
        'hub_unreachable', not 'hub_timeout'."""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Name or service not known")
        with self.assertRaises(HubTransportError) as ctx:
            self.transport._request("GET", "/agents")
        self.assertEqual(ctx.exception.classification, "hub_unreachable")

    def test_hub_transport_error_to_log_data_includes_method_and_code(self):
        """to_log_data() is the structured-log path used by every BaseTransport
        method when an error is swallowed. It must surface the method, error
        message, classification, and status_code (if any)."""
        err = HubTransportError("Hub API 401: bad key", "hub_auth_failed", status_code=401)
        data = err.to_log_data("send_message")
        self.assertEqual(data["method"], "send_message")
        self.assertEqual(data["error"], "Hub API 401: bad key")
        self.assertEqual(data["classification"], "hub_auth_failed")
        self.assertEqual(data["status_code"], 401)

    def test_hub_transport_error_to_log_data_omits_status_code_when_none(self):
        """Errors without an HTTP status (e.g. URLError, invalid response)
        must not include a 'status_code' key in the log payload."""
        err = HubTransportError("Hub returned a non-JSON body", "hub_invalid_response")
        data = err.to_log_data("get_pending_messages")
        self.assertNotIn("status_code", data)
        self.assertEqual(data["method"], "get_pending_messages")
        self.assertEqual(data["classification"], "hub_invalid_response")
