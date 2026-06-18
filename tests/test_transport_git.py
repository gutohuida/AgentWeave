"""Tests for agentweave.transport.git (GitTransport).

The git transport was the highest-risk layer in the Q2 audit (1 CRITICAL,
3 HIGH data-loss bugs). These tests cover the data-loss paths and the
hardening fixes shipped in PR 2:

  H1   — abort push when ls-tree fails after ls-remote succeeded
  H2   — local outbox: never silently drop a message on push failure
  M7   — subprocess.run timeout on every git call (no unbounded hang)
  M11  — seen-set read-modify-write protected by lock()
  M12  — status-update filename uses unambiguous __status__{new}__{ts}.json
  M13  — _iso_compact includes microseconds; UUID suffix is 8 hex chars

All tests mock _run_git / subprocess.run so they run hermetically
without a real git remote.
"""

import re
from contextlib import contextmanager
from unittest.mock import MagicMock

from agentweave.constants import GIT_SEEN_DIR
from agentweave.transport.git import GitTransport, _iso_compact, _run_git

# ---------------------------------------------------------------------------
# Helpers — mock the git subprocess layer
# ---------------------------------------------------------------------------


def _make_git_runner(responses_by_cmd, push_spy=None):
    """Build a fake _run_git.

    Args:
        responses_by_cmd: dict mapping the git subcommand (first arg) to a
            (rc, out, err) tuple OR a callable(args) -> (rc, out, err).
        push_spy: optional dict; if given, the 'count' key is incremented on
            each push call.

    Returns:
        callable suitable for monkeypatch.setattr(..., "_run_git", ...).
    """

    def fake_run(args, stdin_bytes=None):
        if args[0] == "push":
            if push_spy is not None:
                push_spy["count"] = push_spy.get("count", 0) + 1
            resp = responses_by_cmd.get("push", (1, "", "push not configured"))
            if callable(resp):
                return resp(args)
            return resp
        cmd = args[0]
        if cmd in responses_by_cmd:
            resp = responses_by_cmd[cmd]
            if callable(resp):
                return resp(args)
            return resp
        return (1, "", f"unmocked git call: {args}")

    return fake_run


def _happy_push_responses(branch_exists=True, existing_entries="100644 blob old123\told.json\n"):
    """Build the standard 'push succeeds' response set, keyed by subcommand."""
    ls_remote_out = "deadbeef\trefs/heads/agentweave/collab\n" if branch_exists else ""
    return {
        "hash-object": (0, "abc123\n", ""),
        "fetch": (0, "", ""),
        "ls-remote": (0, ls_remote_out, ""),
        "ls-tree": (0, existing_entries, ""),
        "mktree": (0, "newtree\n", ""),
        "commit-tree": (0, "newcommit\n", ""),
        "push": (0, "", ""),
    }


# ---------------------------------------------------------------------------
# H1 — abort push when ls-tree fails after ls-remote succeeded
# ---------------------------------------------------------------------------


def test_push_file_aborts_when_ls_tree_fails_after_ls_remote(monkeypatch):
    """If ls-remote says branch exists but ls-tree fails, _push_file must
    return False WITHOUT calling push.

    Was: silently fell through to the 'new branch' path and built a
    tree containing only the new file, wiping the entire orphan branch.
    """
    t = GitTransport(remote="origin", branch="agentweave/collab")
    push_called = {"count": 0}
    responses = {
        "hash-object": (0, "abc123\n", ""),
        "fetch": (0, "", ""),
        "ls-remote": (0, "deadbeef\trefs/heads/agentweave/collab\n", ""),
        # The critical failure
        "ls-tree": (1, "", "fatal: not a tree object"),
        "push": (0, "", ""),
    }
    monkeypatch.setattr(
        "agentweave.transport.git._run_git",
        _make_git_runner(responses, push_spy=push_called),
    )

    result = t._push_file("test.json", b'{"hi":1}', "test")
    assert result is False
    assert push_called["count"] == 0, "push must NOT be called when ls-tree fails"


def test_push_file_proceeds_when_ls_tree_succeeds(monkeypatch):
    """Sanity: the happy path still works (ls-tree succeeds → push happens)."""
    t = GitTransport(remote="origin", branch="agentweave/collab")
    push_called = {"count": 0}
    monkeypatch.setattr(
        "agentweave.transport.git._run_git",
        _make_git_runner(_happy_push_responses(), push_spy=push_called),
    )

    result = t._push_file("test.json", b'{"hi":1}', "test")
    assert result is True
    assert push_called["count"] == 1


def test_push_file_creates_new_branch_when_ls_remote_empty(monkeypatch):
    """When the branch genuinely doesn't exist, the push must succeed
    (this is the legitimate 'new branch' path that H1 must not break)."""
    t = GitTransport(remote="origin", branch="agentweave/collab")
    push_called = {"count": 0}
    responses = {
        "hash-object": (0, "abc123\n", ""),
        "fetch": (0, "", ""),
        "ls-remote": (0, "", ""),  # empty → branch does not exist
        "mktree": (0, "newtree\n", ""),
        "commit-tree": (0, "newcommit\n", ""),
        "push": (0, "", ""),
    }
    monkeypatch.setattr(
        "agentweave.transport.git._run_git",
        _make_git_runner(responses, push_spy=push_called),
    )

    result = t._push_file("test.json", b'{"hi":1}', "init: agentweave collab branch")
    assert result is True
    assert push_called["count"] == 1


# ---------------------------------------------------------------------------
# H2 — local outbox: never silently drop a message on push failure
# ---------------------------------------------------------------------------


def test_push_failure_writes_to_local_outbox(tmp_path, monkeypatch):
    """When all push retries fail, the message body must be saved to
    .agentweave/outbox/<id>.json so it can be retried later.

    Was: caller got False, message was lost, no recovery path.
    """
    monkeypatch.chdir(tmp_path)
    t = GitTransport(remote="origin", branch="agentweave/collab")
    responses = {
        "hash-object": (0, "abc123\n", ""),
        "fetch": (0, "", ""),
        "ls-remote": (0, "", ""),
        "mktree": (0, "newtree\n", ""),
        "commit-tree": (0, "newcommit\n", ""),
        # Permanent (non-NFF) failure on every retry
        "push": (1, "", "fatal: unable to access remote"),
    }
    monkeypatch.setattr(
        "agentweave.transport.git._run_git",
        _make_git_runner(responses),
    )

    msg = {
        "id": "msg-outbox-1",
        "from": "claude",
        "to": "kimi",
        "content": "do not lose me",
        "subject": "important",
    }
    result = t.send_message(msg)
    assert result is False, "send_message should return False when push fails"

    outbox = tmp_path / ".agentweave" / "outbox"
    assert outbox.exists(), "outbox dir must be created on push failure"
    outbox_files = list(outbox.glob("*.json"))
    assert len(outbox_files) >= 1, f"expected outbox file, got {outbox_files}"
    # The outbox entry should preserve the original message
    import json as _json

    outbox_data = _json.loads(outbox_files[0].read_text(encoding="utf-8"))
    assert outbox_data.get("id") == "msg-outbox-1"
    assert outbox_data.get("content") == "do not lose me"


def test_push_success_leaves_outbox_empty(tmp_path, monkeypatch):
    """If push succeeds, no outbox file should be left behind."""
    monkeypatch.chdir(tmp_path)
    t = GitTransport(remote="origin", branch="agentweave/collab")
    monkeypatch.setattr(
        "agentweave.transport.git._run_git",
        _make_git_runner(_happy_push_responses(branch_exists=False)),
    )

    result = t.send_message(
        {
            "id": "msg-ok-1",
            "from": "claude",
            "to": "kimi",
            "content": "hi",
            "subject": "",
        }
    )
    assert result is True

    outbox = tmp_path / ".agentweave" / "outbox"
    if outbox.exists():
        leftover = list(outbox.glob("*.json"))
        assert leftover == [], f"outbox must be empty on success, got {leftover}"


def test_push_retries_on_non_fast_forward(monkeypatch):
    """A 'non-fast-forward' / 'rejected' push must trigger another retry."""
    t = GitTransport(remote="origin", branch="agentweave/collab")
    push_attempts = {"count": 0}
    push_results = iter(
        [
            (1, "", "[rejected] non-fast-forward"),
            (0, "", ""),
        ]
    )
    responses = dict(_happy_push_responses(branch_exists=False))
    responses["push"] = lambda args: next(push_results)

    monkeypatch.setattr(
        "agentweave.transport.git._run_git",
        _make_git_runner(responses, push_spy=push_attempts),
    )

    result = t._push_file("test.json", b'{"hi":1}', "test")
    assert result is True
    assert push_attempts["count"] == 2, "should retry on NFF"


# ---------------------------------------------------------------------------
# M7 — subprocess.run timeout=30 on every git call
# ---------------------------------------------------------------------------


def test_run_git_passes_timeout_to_subprocess(monkeypatch):
    """Every git subprocess call must have timeout=30 (was: unbounded → hang)."""
    captured_kwargs = {}

    def fake_run(*args, **kwargs):
        captured_kwargs.update(kwargs)
        m = MagicMock()
        m.returncode = 0
        m.stdout = b""
        m.stderr = b""
        return m

    monkeypatch.setattr("agentweave.transport.git.subprocess.run", fake_run)
    _run_git(["status"])

    assert (
        captured_kwargs.get("timeout") == 30
    ), f"_run_git must pass timeout=30, got {captured_kwargs!r}"


def test_run_git_passes_timeout_with_stdin(monkeypatch):
    """The timeout must also be applied when stdin is used (e.g. mktree)."""
    captured_kwargs = {}

    def fake_run(*args, **kwargs):
        captured_kwargs.update(kwargs)
        m = MagicMock()
        m.returncode = 0
        m.stdout = b"abc\n"
        m.stderr = b""
        return m

    monkeypatch.setattr("agentweave.transport.git.subprocess.run", fake_run)
    _run_git(["hash-object", "-w", "--stdin"], stdin_bytes=b"hello")

    assert captured_kwargs.get("timeout") == 30
    assert captured_kwargs.get("input") == b"hello"


# ---------------------------------------------------------------------------
# M11 — seen-set read-modify-write protected by lock()
# ---------------------------------------------------------------------------


def test_save_seen_set_acquires_git_seen_lock(tmp_path, monkeypatch):
    """_save_seen_set must be wrapped in lock() to prevent read-modify-write
    races when two agents share a machine.
    """
    monkeypatch.chdir(tmp_path)
    GIT_SEEN_DIR.mkdir(parents=True, exist_ok=True)
    (GIT_SEEN_DIR / "kimi-seen.txt").write_text("old-id\n", encoding="utf-8")

    t = GitTransport()
    acquired: list = []

    @contextmanager
    def tracking_lock(name, timeout=30):
        acquired.append(name)
        yield

    import agentweave.transport.git as git_mod

    monkeypatch.setattr(git_mod, "lock", tracking_lock)

    t._save_seen_set("kimi", {"old-id", "new-id"})

    assert acquired, "lock() must wrap _save_seen_set"
    assert any(
        "git-seen" in n and "kimi" in n for n in acquired
    ), f"expected lock name containing 'git-seen' and 'kimi', got {acquired!r}"


def test_get_seen_set_acquires_git_seen_lock(tmp_path, monkeypatch):
    """_get_seen_set must also be wrapped in the same lock (read side)."""
    monkeypatch.chdir(tmp_path)
    GIT_SEEN_DIR.mkdir(parents=True, exist_ok=True)
    (GIT_SEEN_DIR / "kimi-seen.txt").write_text("x\n", encoding="utf-8")

    t = GitTransport()
    acquired: list = []

    @contextmanager
    def tracking_lock(name, timeout=30):
        acquired.append(name)
        yield

    import agentweave.transport.git as git_mod

    monkeypatch.setattr(git_mod, "lock", tracking_lock)

    _ = t._get_seen_set("kimi")

    assert acquired, "lock() must wrap _get_seen_set"
    assert any("git-seen" in n for n in acquired)


# ---------------------------------------------------------------------------
# M12 — status-update filename uses unambiguous __status__{new}__{ts}.json
# ---------------------------------------------------------------------------


def test_get_active_tasks_parses_double_underscore_status_format(monkeypatch):
    """Status files with format {task_id}__status__{new}__{ts}.json must be
    parsed correctly even when task_id contains digit-prefixed substrings.

    The old format {task_id}-status-{new}-{ts}.json's non-greedy regex
    confused digits inside task_id with the trailing 4-digit year prefix.

    We use 'in_progress' as the new status so the task stays in the
    'active' list — easier to assert against.
    """
    t = GitTransport()
    task_id = "task-2023-update"
    status_filename = f"{task_id}__status__in_progress__20260309T142301Z.json"
    task_def_filename = "20260309T142301Z-task-for-kimi-aaaaaa.json"
    task_data = {"id": task_id, "assignee": "kimi", "status": "pending"}

    monkeypatch.setattr(t, "_fetch", lambda: True)
    monkeypatch.setattr(t, "list_remote_filenames", lambda: [status_filename, task_def_filename])
    monkeypatch.setattr(
        t,
        "read_remote_file",
        lambda f: task_data if f == task_def_filename else None,
    )

    result = t.get_active_tasks(agent="kimi")
    assert len(result) == 1, f"expected 1 active task, got {len(result)}"
    assert result[0]["status"] == "in_progress", (
        f"expected status='in_progress' from new __status__ format, "
        f"got {result[0].get('status')!r}"
    )


def test_get_active_tasks_old_status_format_with_dashes_parsed_correctly(monkeypatch):
    """Sanity: a status filename with hyphens in the new task_id portion
    (e.g. 'task-with-dashes') is parsed without losing characters.

    With the new __status__{new}__{ts}.json format, splitting on the
    double-underscore marker makes this trivially correct; the old
    format would risk confusion if the status string itself contained
    '-status-' substrings.
    """
    t = GitTransport()
    task_id = "task-with-dashes"
    status_filename = f"{task_id}__status__in_progress__20260309T142301Z.json"
    task_def_filename = "20260309T142301Z-task-for-kimi-aaaaaa.json"
    task_data = {"id": task_id, "assignee": "kimi", "status": "pending"}

    monkeypatch.setattr(t, "_fetch", lambda: True)
    monkeypatch.setattr(t, "list_remote_filenames", lambda: [status_filename, task_def_filename])
    monkeypatch.setattr(
        t,
        "read_remote_file",
        lambda f: task_data if f == task_def_filename else None,
    )

    result = t.get_active_tasks(agent="kimi")
    assert len(result) == 1
    assert result[0]["status"] == "in_progress", (
        f"new format should parse status 'in_progress' from "
        f"'__status__in_progress__...', got {result[0].get('status')!r}"
    )


# ---------------------------------------------------------------------------
# M13 — _iso_compact includes microseconds; UUID suffix is 8 hex chars
# ---------------------------------------------------------------------------


def test_iso_compact_includes_microsecond_precision():
    """_iso_compact should produce YYYYMMDDTHHMMSSffffffZ (with microseconds).

    Was: YYYYMMDDTHHMMSSZ (second precision only). Filenames collided
    when two messages were created in the same second by the same pair.
    """
    s = _iso_compact()
    assert re.match(r"^\d{8}T\d{6}\d{6}Z$", s), f"unexpected iso_compact format: {s!r}"


def test_make_msg_filename_uses_8hex_suffix():
    """Message filenames should use an 8-character hex UUID suffix.

    Was: 6 hex chars (16M space, higher collision risk for chatty pairs).
    """
    t = GitTransport()
    fname = t._make_msg_filename({"from": "claude", "to": "kimi"})
    assert re.match(
        r"^.+-[0-9a-f]{8}\.json$", fname
    ), f"filename should end in -XXXXXXXX.json (8 hex chars), got: {fname!r}"


def test_make_task_filename_uses_8hex_suffix():
    """Task filenames should also use 8-character hex suffix."""
    t = GitTransport()
    fname = t._make_task_filename({"assignee": "kimi"})
    assert re.match(
        r"^.+-[0-9a-f]{8}\.json$", fname
    ), f"filename should end in -XXXXXXXX.json (8 hex chars), got: {fname!r}"


def test_make_msg_filename_uniqueness_under_burst():
    """A burst of 100 message filenames should produce 100 unique names
    (microsecond + 8-hex UUID combination gives enough entropy)."""
    t = GitTransport()
    names = {t._make_msg_filename({"from": "a", "to": "b"}) for _ in range(100)}
    assert len(names) == 100, f"got {len(names)} unique of 100"


# ---------------------------------------------------------------------------
# Filename parsing — recipient extraction
# ---------------------------------------------------------------------------


def test_recipient_from_msg_filename_plain():
    t = GitTransport()
    assert t._recipient_from_msg_filename("20260309T142301Z-claude-kimi-a3f2c1b2.json") == "kimi"


def test_recipient_from_msg_filename_cluster_prefix():
    t = GitTransport()
    # cluster.agent addressing
    assert (
        t._recipient_from_msg_filename("20260309T142301Z-alice.claude-bob.kimi-a3f2c1b2.json")
        == "bob.kimi"
    )


def test_recipient_from_msg_filename_short():
    t = GitTransport()
    assert t._recipient_from_msg_filename("badname.json") == ""


# ---------------------------------------------------------------------------
# Cluster prefix round-trip
# ---------------------------------------------------------------------------


def test_send_message_stamps_cluster_on_from(monkeypatch):
    """When self.cluster is set, the 'from' field is rewritten to
    'cluster.from' if it isn't already prefixed.
    """
    t = GitTransport(cluster="alice")
    captured: dict = {}

    def fake_push(filename, content_bytes, commit_msg):
        import json as _json

        captured["data"] = _json.loads(content_bytes.decode("utf-8"))
        captured["filename"] = filename
        return True

    monkeypatch.setattr(t, "_push_file", fake_push)

    result = t.send_message(
        {"id": "m1", "from": "claude", "to": "kimi", "content": "x", "subject": ""}
    )
    assert result is True
    assert captured["data"]["from"] == "alice.claude"


def test_send_message_does_not_double_prefix(monkeypatch):
    """A 'from' value already containing a dot (cluster prefix) is left alone."""
    t = GitTransport(cluster="alice")
    captured: dict = {}

    def fake_push(filename, content_bytes, commit_msg):
        import json as _json

        captured["data"] = _json.loads(content_bytes.decode("utf-8"))
        return True

    monkeypatch.setattr(t, "_push_file", fake_push)

    t.send_message(
        {
            "id": "m1",
            "from": "bob.claude",
            "to": "kimi",
            "content": "x",
            "subject": "",
        }
    )
    assert captured["data"]["from"] == "bob.claude"


# ---------------------------------------------------------------------------
# Archive message: seen-set must include the right lock
# ---------------------------------------------------------------------------


def test_archive_message_persists_id_to_seen_set(tmp_path, monkeypatch):
    """archive_message must add the message ID to the per-agent seen file."""
    monkeypatch.chdir(tmp_path)
    t = GitTransport()
    msg_id = "msg-archive-1"

    def fake_fetch():
        return True

    def fake_list():
        return ["20260309T142301Z-claude-kimi-a3f2c1b2.json"]

    def fake_read(fname):
        return {
            "id": msg_id,
            "from": "claude",
            "to": "kimi",
            "content": "x",
        }

    monkeypatch.setattr(t, "_fetch", fake_fetch)
    monkeypatch.setattr(t, "list_remote_filenames", fake_list)
    monkeypatch.setattr(t, "read_remote_file", fake_read)

    result = t.archive_message(msg_id)
    assert result is True

    seen_file = GIT_SEEN_DIR / "kimi-seen.txt"
    assert seen_file.exists()
    assert msg_id in seen_file.read_text(encoding="utf-8")


def test_archive_message_returns_false_when_id_not_found(tmp_path, monkeypatch):
    """archive_message returns False when no file has the given ID."""
    monkeypatch.chdir(tmp_path)
    t = GitTransport()
    monkeypatch.setattr(t, "_fetch", lambda: True)
    monkeypatch.setattr(t, "list_remote_filenames", lambda: [])
    monkeypatch.setattr(t, "read_remote_file", lambda f: None)
    assert t.archive_message("nonexistent") is False


# ---------------------------------------------------------------------------
# PR 12 — gap coverage
#
# The earlier 23 tests focused on the data-loss paths (H1/H2/M11/M12/M13)
# and the filename plumbing. These fill the remaining branch surface so
# the test-first discipline is end-to-end, not concentrated on the audit
# findings.
# ---------------------------------------------------------------------------


def test_get_transport_type_returns_git():
    """The transport-type string is 'git' — BaseTransport contract."""
    t = GitTransport()
    assert t.get_transport_type() == "git"


def test_branch_exists_on_remote_true_when_ls_remote_finds_branch(monkeypatch):
    """branch_exists_on_remote must return True when ls-remote finds the ref."""
    t = GitTransport(remote="origin", branch="agentweave/collab")
    responses = {
        "ls-remote": (0, "deadbeef\trefs/heads/agentweave/collab\n", ""),
    }
    monkeypatch.setattr("agentweave.transport.git._run_git", _make_git_runner(responses))
    assert t.branch_exists_on_remote() is True


def test_branch_exists_on_remote_false_when_ls_remote_empty(monkeypatch):
    """branch_exists_on_remote must return False when ls-remote returns nothing."""
    t = GitTransport(remote="origin", branch="agentweave/collab")
    responses = {"ls-remote": (0, "", "")}
    monkeypatch.setattr("agentweave.transport.git._run_git", _make_git_runner(responses))
    assert t.branch_exists_on_remote() is False


def test_save_to_outbox_writes_to_outbox_dir(tmp_path, monkeypatch):
    """_save_to_outbox must create .agentweave/outbox/ if missing and write
    the content under <id>.json."""
    monkeypatch.chdir(tmp_path)
    t = GitTransport()
    t._save_to_outbox(b'{"foo": 1}', "outbox-1")
    outbox = tmp_path / ".agentweave" / "outbox"
    assert outbox.exists()
    files = list(outbox.glob("*.json"))
    assert len(files) == 1
    assert files[0].read_bytes() == b'{"foo": 1}'


def test_remove_from_outbox_clears_file(tmp_path, monkeypatch):
    """_remove_from_outbox must delete the outbox file for the given id."""
    monkeypatch.chdir(tmp_path)
    t = GitTransport()
    t._save_to_outbox(b"hello", "outbox-2")
    outbox = tmp_path / ".agentweave" / "outbox"
    assert any(outbox.glob("*.json"))
    t._remove_from_outbox("outbox-2")
    # File for outbox-2 should be gone.
    leftovers = [p for p in outbox.glob("*.json") if "outbox-2" in p.name]
    assert leftovers == []


def test_matches_agent_plain_name():
    """_matches_agent must treat a plain 'kimi' recipient as matching
    the 'kimi' agent (no cluster prefix)."""
    t = GitTransport()
    assert t._matches_agent("kimi", "kimi") is True
    assert t._matches_agent("kimi", "claude") is False


def test_matches_agent_with_cluster_prefix():
    """_matches_agent must match '<our_cluster>.<our_agent>' recipient when
    self.cluster is set. Without a cluster, the function only matches plain
    agent names (backward-compat for single-workspace deployments)."""
    # No cluster: only plain names match.
    t = GitTransport()
    assert t._matches_agent("kimi", "kimi") is True
    assert t._matches_agent("bob.kimi", "kimi") is False

    # With a cluster: '<cluster>.<agent>' recipient matches for this agent.
    t_clustered = GitTransport(cluster="bob")
    assert t_clustered._matches_agent("bob.kimi", "kimi") is True
    assert t_clustered._matches_agent("bob.kimi", "bob") is False
    assert t_clustered._matches_agent("alice.kimi", "kimi") is False
    # Plain name still matches (backward compat).
    assert t_clustered._matches_agent("kimi", "kimi") is True


def test_get_pending_messages_filters_by_recipient(tmp_path, monkeypatch):
    """get_pending_messages must return only messages whose recipient matches
    the agent and whose id is NOT in the seen set."""
    monkeypatch.chdir(tmp_path)
    t = GitTransport()

    msg_to_kimi = {
        "id": "m-kimi-1",
        "from": "claude",
        "to": "kimi",
        "content": "for kimi",
    }
    msg_to_claude = {
        "id": "m-claude-1",
        "from": "kimi",
        "to": "claude",
        "content": "for claude",
    }
    seen_id = "m-seen-1"
    msg_to_kimi_seen = {
        "id": seen_id,
        "from": "claude",
        "to": "kimi",
        "content": "already seen",
    }
    monkeypatch.setattr(t, "_fetch", lambda: True)
    monkeypatch.setattr(
        t,
        "list_remote_filenames",
        lambda: [
            "20260309T142301Z-claude-kimi-aaaaaaaa.json",
            "20260309T142301Z-kimi-claude-bbbbbbbb.json",
            "20260309T142301Z-claude-kimi-cccccccc.json",
        ],
    )
    monkeypatch.setattr(
        t,
        "read_remote_file",
        lambda f: (
            msg_to_kimi
            if "aaaaaaaa" in f
            else msg_to_claude if "bbbbbbbb" in f else msg_to_kimi_seen
        ),
    )
    # Pre-seed the seen set with m-seen-1.
    GIT_SEEN_DIR.mkdir(parents=True, exist_ok=True)
    (GIT_SEEN_DIR / "kimi-seen.txt").write_text(seen_id + "\n", encoding="utf-8")

    result = t.get_pending_messages("kimi")
    ids = [m["id"] for m in result]
    assert "m-kimi-1" in ids
    assert "m-seen-1" not in ids, "seen id must be filtered out"
    assert "m-claude-1" not in ids, "wrong recipient must be filtered out"
