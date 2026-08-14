"""A runtime that dies says what it was doing.

`{"error": "app-server process ended"}` is true of every transport failure and distinguishes none
of them. In the loop-7 run a Codex agent failed four times in a row with that exact string, and
working out why meant noticing which *other* agents still worked — a crash, a missing binary, a
rejected credential and an unresumable thread all produce the same sentence.

Three facts were in scope at the raise and thrown away: the exit status, the in-flight JSON-RPC
method (discarded because `_pending` held only the future), and the child's stderr — which has
been piped since this class was written and read by nobody. That last one is not merely a lost
diagnostic: an undrained pipe fills, and the child then blocks writing to it.

These tests drive real subprocesses. A fake cannot demonstrate a pipe filling.
"""

import asyncio
import sys

import pytest

from hub.codex_appserver import STDERR_TAIL_LINES, AppServerError, AppServerProcess


async def spawn_child(script: str) -> AppServerProcess:
    """An app-server stand-in: a real process on real pipes, running *script*."""
    return await AppServerProcess.spawn([sys.executable, "-u", "-c", script])


@pytest.mark.asyncio
async def test_process_death_names_the_exit_code_and_the_pending_method():
    """The failure that cost loop 7 an afternoon, with the three facts attached."""
    session = await spawn_child(
        "import sys; sys.stdin.readline(); sys.stderr.write('auth failed: no credentials\\n'); "
        "sys.exit(127)"
    )
    try:
        with pytest.raises(AppServerError) as caught:
            await session.request("thread/resume", {"threadId": "t-1"}, timeout=10)
    finally:
        await session.close()

    error = caught.value
    assert error.exit_code == 127
    assert error.method == "thread/resume"
    assert "auth failed" in error.stderr_tail


@pytest.mark.asyncio
async def test_the_error_reads_as_one_sentence_for_existing_handlers():
    """`str(exc)` alone has to carry it, or nothing downstream reports it.

    `Run.error`, the `run_failed` payload and an abandoned queue entry's reason all read the
    string and nothing else. Composing into the message is what lets them all improve at once.
    """
    session = await spawn_child(
        "import sys; sys.stdin.readline(); sys.stderr.write('boom\\n'); sys.exit(3)"
    )
    try:
        with pytest.raises(AppServerError) as caught:
            await session.request("thread/start", {}, timeout=10)
    finally:
        await session.close()

    rendered = str(caught.value)
    assert "exit 3" in rendered
    assert "thread/start" in rendered
    assert "boom" in rendered


@pytest.mark.asyncio
async def test_the_stderr_tail_is_bounded():
    """A crash loop must not grow the buffer without limit."""
    session = await spawn_child(
        "import sys\n"
        "for i in range(1000): sys.stderr.write('line %d\\n' % i)\n"
        "sys.stdin.readline()\n"
    )
    try:
        # Wait for the child to finish writing, rather than sampling it mid-stream.
        for _ in range(200):
            if any("line 999" in line for line in session._stderr):
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("the drain never saw the child's last line")

        assert len(session._stderr) == STDERR_TAIL_LINES, "the deque must cap the retained lines"

        tail = session.stderr_tail()
        assert "line 999" in tail, "the tail must be the *end* of the stream"
        assert "line 0 " not in tail, "the beginning must have been dropped"
        assert len(session.stderr_tail(limit=200)) <= 201, "bounded for an event payload"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_stderr_is_drained_so_a_chatty_child_cannot_block():
    """The second live bug in the same lines.

    A pipe nobody reads fills at roughly 64KB, and the child then blocks *writing to it* — so the
    process being diagnosed is hung by the diagnosis going uncollected. This child writes far more
    than a pipe buffer holds and then answers a request; without the drain it never gets that far.
    """
    session = await spawn_child(
        "import sys, json\n"
        "sys.stderr.write('x' * 500000)\n"
        "sys.stderr.flush()\n"
        "line = sys.stdin.readline()\n"
        "msg = json.loads(line)\n"
        "sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':{'ok':True}}) + '\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stdin.readline()\n"
    )
    try:
        answered = await session.request("initialize", {}, timeout=15)
        assert answered["result"] == {"ok": True}, "the child got past its own stderr write"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_a_clean_response_is_unaffected():
    """The common path still resolves normally — the diagnostics are only for the failure."""
    session = await spawn_child(
        "import sys, json\n"
        "line = sys.stdin.readline()\n"
        "msg = json.loads(line)\n"
        "sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':{'v':1}}) + '\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stdin.readline()\n"
    )
    try:
        answered = await session.request("initialize", {}, timeout=15)
        assert answered["result"] == {"v": 1}
        assert session.returncode is None, "a healthy child is still running"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_close_is_still_idempotent_with_the_drain_running():
    """`close` now cancels two tasks rather than one, and is called from a `finally`."""
    session = await spawn_child("import sys; sys.stdin.readline()")
    await session.close()
    await session.close()
    assert session.returncode is not None


def test_the_run_failed_payload_carries_what_the_error_knows():
    """The transport-failure broadcast used to carry only a string.

    The normal-completion broadcast carries `exit_code`/`conversation_id`, so the two shapes
    disagreed exactly where diagnosis is hardest. `getattr` is used because the same `except`
    also catches `FileNotFoundError`/`OSError`, which carry none of these — an absent fact must be
    reported as absent rather than invented.
    """
    from hub.api.v1.agent_trigger import _transport_failure_fields

    rich = AppServerError("app-server process ended", exit_code=127, method="thread/resume")
    fields = _transport_failure_fields(rich, "conv-1")
    assert fields["exit_code"] == 127
    assert fields["method"] == "thread/resume"
    assert fields["conversation_id"] == "conv-1"
    assert "exit 127" in fields["error"]

    plain = FileNotFoundError("codex not found")
    fields = _transport_failure_fields(plain, None)
    assert fields["exit_code"] is None
    assert fields["method"] is None
    assert fields["error"] == "codex not found"
