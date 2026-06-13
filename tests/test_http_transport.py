"""Tests for HttpTransport — mocks urllib to avoid network calls."""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from agentweave.transport.http import HttpTransport, HubTransportError


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


if __name__ == "__main__":
    unittest.main()
