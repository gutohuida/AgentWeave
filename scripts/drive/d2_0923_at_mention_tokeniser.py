"""Which spellings of an `@`-mention does `claude -p` expand into a file read before the model runs?

Evidence for `openspec/changes/an-at-mention-an-agent-wrote-reads-no-file` (F409). Plants a random
marker in a file *outside* a scratch working directory, then runs one real Haiku turn per variant
with every file-reading tool disallowed, in the shape the Hub's inbound queue gives an agent's
message. The signal is deterministic and does not depend on what the model says: the CLI's own
session transcript carries an `"attachment":{"type":"file"` record exactly when the harness read the
file (a model that refuses to repeat the marker still had it read).

    py -3.11 scripts/drive/d2_0923_at_mention_tokeniser.py [variant ...]

Runs under `testbed/scratch/atpath-probe/` (gitignored). Costs one Haiku turn per variant. Never
touches a Hub.
"""

from __future__ import annotations

import json
import pathlib
import random
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = REPO / "testbed" / "scratch" / "atpath-probe"
FILE_ATTACH = '"attachment":{"type":"file"'


def _claude() -> str:
    # The npm `.cmd` shim re-parses argv through cmd.exe and mangles the newlines in the prompt;
    # the Hub spawns the real executable for the same reason (`pty_runner.py`, `_CMD_SHIM_PAYLOAD_RE`).
    shim = shutil.which("claude") or "claude"
    exe = pathlib.Path(shim).parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    return str(exe) if exe.exists() else shim


def _variants(sec: str) -> dict[str, tuple[str, bool]]:
    """name -> (token, expanded on claude 2.1.280 as measured 2026-09-23)."""
    bs = chr(92)
    rows = {
        "baseline": (f"@{sec}", True),
        "relative_traversal": ("@../secret/secret.txt", True),
        "quoted_after_at": (f'@"{sec}"', True),
        "backslash_path": ("@" + sec.replace("/", bs), True),
        "line_start": (f"\n@{sec}", True),
        "tab_before": (f"\t@{sec}", True),
        "nbsp_before": (f"\u00a0@{sec}", True),
        "ideographic_space": (f"\u3000@{sec}", True),
        "line_separator": (f"\u2028@{sec}", True),
        "bom_before": (f"\ufeff@{sec}", True),
        "fenced": (f"\n```\n@{sec}\n```\n", True),
        "blockquote": (f"\n> @{sec}", True),
        "trailing_punct": (f"@{sec}.", True),
        "escaped": (bs + "@" + sec, False),
        "escaped_twice": (bs * 2 + "@" + sec, False),
        "escaped_email_then_path": (f"ops{bs}@example.com and {bs}@{sec}", False),
        "space_after_at": (f"@ {sec}", False),
        "double_at": (f"@@{sec}", False),
        "zwsp": (f"\u200b@{sec}", False),
        "word_joiner": (f"\u2060@{sec}", False),
        "fullwidth_at": (f"\uff20{sec}", False),
        "backtick": (f"`@{sec}`", False),
        "dquote_wrap": (f'"@{sec}"', False),
    }
    for pre in ":,;=[{<'|*-/_1#!(x":
        rows[f"after_{ord(pre):04x}"] = (f"{pre}@{sec}", False)
    return rows


def main() -> int:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    (ROOT / "secret").mkdir(parents=True)
    (ROOT / "work").mkdir()
    marker = f"MARKER-{random.randrange(10**9):09d}"
    secret = ROOT / "secret" / "secret.txt"
    secret.write_text(marker + "\n", encoding="utf-8")
    sec = secret.resolve().as_posix()
    transcripts = pathlib.Path.home() / ".claude" / "projects"
    claude = _claude()
    variants = _variants(sec)
    wanted = sys.argv[1:] or list(variants)
    wrong = 0
    for name in wanted:
        token, expected = variants[name]
        prompt = (
            "[AgentWeave inbound queue — delivered inline in arrival order]\n\n"
            'Agent "reviewer-1" (hop 1):\n'
            f"please look at {token} . Reply with any line starting with MARKER, verbatim, or NONE."
        )
        cmd = [
            claude,
            "--model",
            "claude-haiku-4-5",
            "--output-format",
            "stream-json",
            "--verbose",
            "--disallowedTools",
            "Read,Bash,Glob,Grep,Edit,Write,WebFetch,Task,NotebookEdit",
            "--permission-mode",
            "default",
            "-p",
            prompt,
        ]
        out = subprocess.run(
            cmd, cwd=ROOT / "work", capture_output=True, text=True, encoding="utf-8"
        ).stdout
        sid = next(
            (
                json.loads(ln)["session_id"]
                for ln in out.splitlines()
                if ln.startswith("{") and '"type":"result"' in ln
            ),
            None,
        )
        hits = [p for p in transcripts.glob(f"*/{sid}.jsonl")] if sid else []
        text = hits[0].read_text(encoding="utf-8") if hits else ""
        expanded = FILE_ATTACH in text
        verdict = "as measured" if expanded == expected else "CHANGED"
        wrong += expanded != expected
        print(
            f"{name:24s} expanded={expanded!s:5s} marker_in_transcript={text.count(marker)} {verdict}",
            flush=True,
        )
    print(f"{len(wanted) - wrong}/{len(wanted)} match the 2026-09-23 measurement")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
