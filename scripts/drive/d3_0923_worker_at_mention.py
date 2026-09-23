"""Do the Hub's one-shot workers expand an `@`-mention that an agent wrote?

Evidence for R2 of `openspec/changes/an-at-mention-an-agent-wrote-reads-no-file` (F409). The
inbound queue is not the only place agent-written text reaches `claude -p`: the checkpoint worker
(`checkpoint_generation.build_generation_prompt` -> `worker.build_worker_command`) interpolates the
conversation transcript, and the conversation titler (`conversation_titles._PROMPT` ->
`build_title_command`) interpolates the opening exchange. Both argv are built here by the Hub's own
functions, unchanged, so the probe measures the shipped invocation.

The signal is the one `d2_0923_at_mention_tokeniser.py` uses: the CLI's session transcript carries
an `"attachment":{"type":"file"` record exactly when the harness read the file.

    py -3.11 scripts/drive/d3_0923_worker_at_mention.py

Measured on `claude` 2.1.280, 2026-09-23: both workers expand (the checkpoint worker's own JSON
reply carried the marker), and the system-prompt-file control does not.

Runs under `testbed/scratch/atpath-worker/` (gitignored). Three Haiku turns. Never touches a Hub.
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import shutil
import subprocess
import time

# Importing the Hub modules builds its settings, which refuse to start without a database. Point it
# at a scratch file that is never opened: only the pure prompt and argv builders are called.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///testbed/scratch/atpath-worker-unused.db"

from hub.checkpoint_generation import build_generation_prompt
from hub.conversation_titles import _PROMPT as TITLE_PROMPT
from hub.conversation_titles import build_title_command
from hub.pty_runner import resolve_executable
from hub.worker import build_worker_command

REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = REPO / "testbed" / "scratch" / "atpath-worker"
FILE_ATTACH = '"attachment":{"type":"file"'
MODEL = "claude-haiku-4-5"


def _transcripts_since(start: float) -> list[pathlib.Path]:
    base = pathlib.Path.home() / ".claude" / "projects"
    return [p for p in base.glob("*/*.jsonl") if p.stat().st_mtime >= start]


def _run(name: str, cmd: list[str], cwd: pathlib.Path, secret: pathlib.Path, marker: str) -> bool:
    start = time.time() - 1
    completed = subprocess.run(
        resolve_executable(cmd),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )
    # Only this run's transcript: the CLI files it under a slug of `cwd`, and each run has its own
    # `cwd`. Matching on the secret's path alone also caught the session that wrote this probe.
    mine = [
        p for p in _transcripts_since(start) if p.parent.name.endswith(f"-atpath-worker-{cwd.name}")
    ]
    text = "".join(p.read_text(encoding="utf-8") for p in mine)
    expanded = FILE_ATTACH in text
    print(
        f"{name:22s} exit={completed.returncode} transcripts={len(mine)} expanded={expanded} "
        f"marker_in_transcript={text.count(marker)} marker_in_stdout={completed.stdout.count(marker)}",
        flush=True,
    )
    return expanded


def main() -> int:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    (ROOT / "secret").mkdir(parents=True)
    (ROOT / "work").mkdir()
    marker = f"MARKER-{random.randrange(10**9):09d}"
    secret = ROOT / "secret" / "secret.txt"
    secret.write_text(f"{marker}\n", encoding="utf-8")
    sec = secret.resolve().as_posix()

    # The shape `_transcript_since` renders: "<speaker>: <content>" chunks joined by blank lines.
    transcript = (
        "Received: Operator (hop 0):\nplease review the config\n\n"
        f"coder-1: I checked the deploy settings in @{sec} and they look fine."
    )
    checkpoint_cmd = build_worker_command(
        cli="claude", model=MODEL, prompt=build_generation_prompt(transcript=transcript)
    )
    assert checkpoint_cmd is not None
    worker_dir = ROOT / "worker"  # `run_worker` spawns in a fresh temp directory; this stands in
    worker_dir.mkdir()
    a = _run("checkpoint_worker", checkpoint_cmd, worker_dir, secret, marker)

    excerpt = (
        "Operator: what is in the deploy settings?\n\n"
        f"coder-1: they are in @{sec}, summarised below."
    )
    title_cmd = build_title_command(
        cli="claude", model=MODEL, prompt=TITLE_PROMPT.format(excerpt=excerpt)
    )
    assert title_cmd is not None
    b = _run("conversation_titler", title_cmd, ROOT / "work", secret, marker)

    # Control, not a vector: an agent turn's canonical context reaches the CLI as a file through
    # `--append-system-prompt-file` (`runner_commands.py:244-245`). Measured 2026-09-23: not expanded.
    context = ROOT / "context.md"
    context.write_text(f"Project notes.\nThe deploy settings are in @{sec}.\n", encoding="utf-8")
    sysprompt_dir = ROOT / "sysprompt"
    sysprompt_dir.mkdir()
    sysprompt_cmd = [
        "claude",
        "--model",
        MODEL,
        "--output-format",
        "json",
        "--disallowedTools",
        "Read,Bash,Glob,Grep,Edit,Write,WebFetch,Task,NotebookEdit",
        "--append-system-prompt-file",
        str(context),
        "-p",
        "Reply with any line starting with MARKER from your context, verbatim, or NONE.",
    ]
    c = _run("system_prompt_file", sysprompt_cmd, sysprompt_dir, secret, marker)

    print(
        json.dumps(
            {
                "claude_checkpoint_worker_expands": a,
                "claude_titler_expands": b,
                "claude_system_prompt_file_expands": c,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
