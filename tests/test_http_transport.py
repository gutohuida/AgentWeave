"""Tests for HttpTransport — mocks urllib to avoid network calls."""

import json
import unittest
from unittest.mock import MagicMock, patch

from agentweave.transport.http import HttpTransport


def _make_response(data, status=200):
    """Return a context-manager mock that behaves like urllib.urlopen."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode()
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


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


if __name__ == "__main__":
    unittest.main()
