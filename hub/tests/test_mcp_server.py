"""Tests for hub.mcp_server — covers M23 (urlopen timeout).

The MCP server's internal _hub_request helper makes authenticated calls
to the Hub REST API. Without a timeout, a slow Hub will hang the MCP
server indefinitely (it lives in the same process as the watchdog).

M23: _hub_request must pass timeout=10 to urllib.request.urlopen.
"""

from unittest.mock import MagicMock


def _ok_response(body=b'{"ok": true}'):
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_hub_request_passes_timeout_10_to_urlopen(monkeypatch):
    """M23: every urlopen call from _hub_request must use timeout=10."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["timeout"] = timeout
        return _ok_response()

    # Patch the module-level urllib.request.urlopen reference.
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("HUB_API_KEY", "test-key")
    monkeypatch.setenv("HUB_PROJECT_ID", "proj-test")

    # Import lazily so the env-var setup above is in place.
    from hub.mcp_server import _hub_request

    _hub_request("GET", "/agents")

    assert (
        captured.get("timeout") == 10
    ), f"_hub_request must pass timeout=10 to urlopen, got {captured.get('timeout')!r}"


def test_hub_request_passes_timeout_on_post(monkeypatch):
    """The timeout must also apply on POST (where a slow body upload is the risk)."""
    captured = {}

    def fake_urlopen(req, timeout=None, data=None):
        captured["timeout"] = timeout
        return _ok_response(b'{"id": "x"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("HUB_API_KEY", "test-key")
    monkeypatch.setenv("HUB_PROJECT_ID", "proj-test")

    from hub.mcp_server import _hub_request

    _hub_request("POST", "/messages", body={"from": "a", "to": "b", "subject": "s", "content": "c"})

    assert captured.get("timeout") == 10
