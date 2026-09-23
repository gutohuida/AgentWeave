"""Does a one-shot worker still return usable JSON once its prompt's at-signs are escaped?

Evidence for R3 of `openspec/changes/an-at-mention-an-agent-wrote-reads-no-file` (F409). Design D7
(written in R2) neutralises a worker's whole prompt, turning every `@` into `\\@`. Both checkpoint
workers answer with a JSON object that `worker._interpret` parses with `extract_json_object`, and
`\\@` is not a valid JSON string escape. A reply that copies an escaped at-sign verbatim into a
string value is therefore not an object at all. This probe measures what Haiku actually writes.

Every argv is built by the Hub's own builders, and every reply goes through the Hub's own parsing
(`parse_envelope`, `extract_json_object`, `model_validate`). Only the neutralisation is simulated,
as `str.replace("@", "\\\\@")`, which is D2's rule.

    py -3.11 scripts/drive/d4_0923_worker_json_escape.py [runs-per-variant]

Runs under `testbed/scratch/atpath-json/` (gitignored). Never touches a Hub.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///testbed/scratch/atpath-json-unused.db"

from hub.checkpoint_generation import (  # noqa: E402
    _PROBE_PROMPT,
    CheckpointBody,
    ProbeAnswers,
    build_generation_prompt,
)
from hub.pty_runner import resolve_executable  # noqa: E402
from hub.worker import build_worker_command, extract_json_object, parse_envelope  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = REPO / "testbed" / "scratch" / "atpath-json"
MODEL = "claude-haiku-4-5"

# R2's proposed generation-template rule (design D7), inserted as the last rule for variant `rule`.
R2_RULE = (
    "- At-signs in the material below have a backslash in front of them that the original did "
    "not have; write them without it.\n"
)

FILES = ["packages/@scope/ui/index.ts", "src/app.py", "docs/@types/notes.md"]


def neutralise(text: str) -> str:
    return text.replace("@", "\\@")


def _spawn(prompt: str, cwd: pathlib.Path) -> tuple[str, str]:
    cmd = build_worker_command(cli="claude", model=MODEL, prompt=prompt)
    assert cmd is not None
    done = subprocess.run(
        resolve_executable(cmd),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )
    answer, _usage, error = parse_envelope("claude", done.stdout)
    return answer or "", error or ""


def _interpret(answer: str, model):
    payload = extract_json_object(answer)
    if payload is None:
        return "unparseable", None
    try:
        return "ok", model.model_validate(payload)
    except Exception:  # noqa: BLE001 -- the outcome is what is being measured
        return "schema_invalid", None


def _strings(parsed) -> str:
    return json.dumps(parsed.model_dump(), ensure_ascii=False) if parsed is not None else ""


def generation(variant: str, cwd: pathlib.Path) -> dict:
    transcript = (
        "Received: Operator (hop 0):\nplease fix the ui package and mail ops@example.com when done\n\n"
        "coder-1: I changed packages/@scope/ui/index.ts and added a @pytest.fixture in "
        "tests/conftest.py. I asked @reviewer-1 to look at docs/@types/notes.md next."
    )
    prompt = build_generation_prompt(transcript=transcript)
    if variant == "rule":
        prompt = prompt.replace(
            "- If you do not know something",
            R2_RULE + "- If you do not know something",
            1,
        )
    answer, error = _spawn(neutralise(prompt), cwd)
    outcome, parsed = _interpret(answer, CheckpointBody)
    text = _strings(parsed)
    return {
        "kind": "generation",
        "variant": variant,
        "envelope_error": error,
        "outcome": outcome,
        "raw_backslash_at": answer.count("\\@"),
        "stored_backslash_at": text.count("\\\\@"),
        "stored_at": text.count("@"),
        "raw_head": answer[:160].replace("\n", " "),
    }


def _norm_today(values):
    return {str(v).strip().replace("\\", "/").lstrip("./") for v in values if str(v).strip()}


def _norm_r2(values):
    # R2's D7: undo the escape in the answers only, then today's `_normalise`.
    return _norm_today([str(v).replace("\\@", "@") for v in values])


def _norm_symmetric(values):
    # R3's candidate: one rule applied to both sides; separators before an at-sign are dropped.
    return {
        re.sub(r"/+@", "@", str(v).strip().replace("\\", "/")).lstrip("./")
        for v in values
        if str(v).strip()
    }


def probe(cwd: pathlib.Path) -> dict:
    rendered = "\n".join(
        [
            "# Checkpoint ck-probe",
            "",
            "Conversation: conv-1",
            "Agent: coder-1",
            "Trigger: manual",
            "Status: generated",
            "",
            "## Files changed",
            "",
            *[f"- {p}" for p in FILES],
            "",
            "## Tasks",
            "",
            "_No tasks assigned._",
            "",
            "## Open questions",
            "",
            "_None outstanding._",
            "",
            "## Objective",
            "",
            "Fix the ui package; mail ops@example.com when done.",
        ]
    )
    answer, error = _spawn(neutralise(_PROBE_PROMPT.format(rendered=rendered)), cwd)
    outcome, parsed = _interpret(answer, ProbeAnswers)
    graded = {}
    if parsed is not None:
        for name, norm in (
            ("today", _norm_today),
            ("r2_undo", _norm_r2),
            ("symmetric", _norm_symmetric),
        ):
            expected, reported = norm(FILES), norm(parsed.files_changed)
            graded[name] = "passed" if expected == reported else "failed"
    return {
        "kind": "probe",
        "envelope_error": error,
        "outcome": outcome,
        "answers": parsed.files_changed if parsed is not None else None,
        "graded": graded,
        "raw_head": answer[:200].replace("\n", " "),
    }


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    rows = []
    for i in range(runs):
        for variant in ("plain", "rule"):
            cwd = ROOT / f"gen-{variant}-{i}"
            cwd.mkdir()
            rows.append(generation(variant, cwd))
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
        cwd = ROOT / f"probe-{i}"
        cwd.mkdir()
        rows.append(probe(cwd))
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
