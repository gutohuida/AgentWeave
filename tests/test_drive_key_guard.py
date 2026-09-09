"""`scripts/drive/aw.py` must refuse to build a request without AW_KEY, and no drive script
may carry a Hub key as a literal.

Both halves are recurrences, not hypotheticals. A live `aw_live_...` key sat in `aw.py` as a
default from the file's first commit until 2026-09-07 in a public repository; the sweep that
removed it missed two sibling scripts, because the sweep was assembled from what a reader noticed
rather than from a grep. And the comment left behind claimed an unset key "fails loudly below"
when it did not -- the call returned a 401 and exit code 0.

`scripts/` is in neither of CI's lint path lists (ruff covers `src/ hub/ tests/`, black covers
`src/ hub/hub/ hub/tests/ tests/`), so nothing else in CI reads this directory at all. This file
is the only gate on it.
"""

import importlib.util
import re
from pathlib import Path

import pytest

DRIVE = Path(__file__).resolve().parents[1] / "scripts" / "drive"
AW = DRIVE / "aw.py"

# The Hub's own key format (`aw_live_{random32}`). Matches a real key, not the word.
KEY_LITERAL = re.compile(r"aw_live_[0-9a-f]{32}")


def _load_aw(monkeypatch, key):
    """Import `aw.py` fresh under a chosen AW_KEY. It reads the environment at import time."""
    monkeypatch.setenv("AW_KEY", key)
    spec = importlib.util.spec_from_file_location("aw_under_test", AW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_drive_script_carries_a_hub_key_literal():
    offenders = [
        f"{p.name}:{i}"
        for p in sorted(DRIVE.glob("*.py"))
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if KEY_LITERAL.search(line)
    ]
    assert offenders == [], f"Hub key literals in tracked drive scripts: {offenders}"


def test_an_unset_key_fails_before_any_http_call(monkeypatch):
    """Locally, not as a 401 -- and the tripwire is what tells those two apart.

    A fourth mutation was tried and this gate does NOT catch it: moving `require_key()` below the
    `Request` construction, so the request object is built and then abandoned. That is deliberate.
    Nothing reaches the network either way, which is the property the 401 defect was about; a gate
    that also pinned the call's internal ordering would fail on a harmless refactor.
    """
    aw = _load_aw(monkeypatch, "")
    attempted = []
    monkeypatch.setattr(aw.urllib.request, "urlopen", lambda *a, **k: attempted.append(a) or None)

    # SystemExit, not RuntimeError: `api()` and its callers are full of `except Exception`, and a
    # configuration error one of those can swallow is not a loud failure.
    with pytest.raises(SystemExit) as exc:
        aw.api("GET", "/projects")

    assert "AW_KEY" in str(exc.value)
    assert attempted == [], "the guard let a request reach the network"


def test_a_key_that_is_set_is_not_refused(monkeypatch):
    """The guard gates on emptiness. A blanket refusal would pass the test above and be useless."""
    aw = _load_aw(monkeypatch, "aw_live_" + "0" * 32)
    seen = {}

    class _Resp:
        status = 200

        def read(self):
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _urlopen(req, *a, **k):
        seen["auth"] = req.get_header("Authorization")
        return _Resp()

    monkeypatch.setattr(aw.urllib.request, "urlopen", _urlopen)

    assert aw.api("GET", "/projects") == (200, [])
    assert seen["auth"] == "Bearer aw_live_" + "0" * 32


# `os.environ.get("AW_KEY", <default>)`, with the default captured. Non-greedy up to the closing
# paren: every call site in `scripts/drive/` fits on one line, and a multi-line one would simply
# not match rather than match wrongly.
AW_KEY_DEFAULT = re.compile(r"""os\.environ\.get\(\s*["']AW_KEY["']\s*,\s*(?P<default>[^)]*)\)""")


def test_no_drive_script_defaults_the_key_to_anything():
    """The property is the default, not the shape of what is defaulted.

    `test_no_drive_script_carries_a_hub_key_literal` above gates on `aw_live_[0-9a-f]{32}` -- a
    real key's shape. Four scripts sat under it for a day carrying
    `os.environ.get("AW_KEY", "aw_live_<33 non-hex characters>")`: placeholder-shaped, so the
    regex walked past, while the behaviour was exactly the one the guard exists to prevent -- an
    unset AW_KEY sends a bogus Bearer token, the Hub answers 401, and the script carries on.

    So this gate asks the shape-independent question instead. A drive script may read AW_KEY with
    no default (`os.environ.get("AW_KEY")`) or with an empty one -- both leave the emptiness
    visible to `require_key()` or to the script's own `if not KEY` check. It may not substitute a
    value of any shape, because a substituted value is a key the script never had.
    """
    offenders = []
    for p in sorted(DRIVE.glob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = AW_KEY_DEFAULT.search(line)
            if m and m.group("default").strip() not in ('""', "''"):
                offenders.append(f"{p.name}:{i}")
    assert offenders == [], (
        "drive scripts substituting a value for an unset AW_KEY "
        f"(use `require_key()` or an empty default): {offenders}"
    )
