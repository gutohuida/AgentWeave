"""the-codex-models-offered-are-the-ones-its-cli-lists — the Codex half of the catalog is read
from the installed CLI's own model cache at runtime, with the literal `CATALOG["codex"]` as the
fallback (design D1/D2/D4). Design tests 1-8; test 9 (the runner form's source line) is
`hub/ui/src/__tests__/...` (vitest).

The `_no_real_codex_model_cache` autouse fixture (conftest.py, design D4) points
`model_catalog._codex_cache_path` at a nonexistent file under this test's own `tmp_path` and
clears the module's memo, so every test here starts on the literal fallback and only sees a cache
when it writes one with `write_cache`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Sequence

import pytest

import hub.model_catalog as model_catalog
from hub.model_catalog import (
    CATALOG,
    codex_catalog_source,
    context_window_for_model,
    get_provider,
    model_context_window,
)

P = "/api/v1/projects/proj-test"


def _cache_path() -> Path:
    """The path the fixture pinned `_codex_cache_path` to for the running test."""
    return model_catalog._codex_cache_path()


def write_cache(
    models: Sequence[dict],
    *,
    fetched_at: str = "2026-09-23T10:10:51Z",
    client_version: str = "0.146.0",
    path: Optional[Path] = None,
) -> Path:
    """A `models_cache.json` in the shape the Codex CLI actually writes (real-cache keys: keeps
    `etag` even though the reader ignores it, to match the file's real shape)."""
    target = path if path is not None else _cache_path()
    target.write_text(
        json.dumps(
            {
                "fetched_at": fetched_at,
                "etag": 'W/"deadbeef"',
                "client_version": client_version,
                "models": list(models),
            }
        ),
        encoding="utf-8",
    )
    return target


def entry(
    slug: str,
    *,
    display_name: Optional[str] = None,
    context_window: Optional[int] = 272_000,
    visibility: str = "list",
    priority: Optional[int] = None,
) -> dict:
    d = {
        "slug": slug,
        "display_name": display_name if display_name is not None else slug.upper(),
        "context_window": context_window,
        "visibility": visibility,
    }
    if priority is not None:
        d["priority"] = priority
    return d


# --- test 1: priority order, visibility filter, hidden entries excluded --------------------------


def test_a_cache_is_offered_in_priority_order_with_the_lowest_first_as_default():
    write_cache(
        [
            entry("m-h", visibility="hide", priority=0),
            entry("m-b", priority=2),
            entry("m-a", priority=1),
        ]
    )
    codex = get_provider("codex")
    assert [m.id for m in codex.models] == ["m-a", "m-b"]
    assert next(m for m in codex.models if m.id == "m-a").default is True
    assert next(m for m in codex.models if m.id == "m-b").default is False
    assert next(m for m in codex.models if m.id == "m-a").label == "M-A"
    assert next(m for m in codex.models if m.id == "m-a").context_window == 272_000


# --- test 2: no cache falls back to the literal, with a reason --------------------------------


def test_no_cache_gives_exactly_the_literal_ids_and_a_reason():
    codex = get_provider("codex")
    assert [m.id for m in codex.models] == [m.id for m in CATALOG["codex"].models]
    source = codex_catalog_source()
    assert source.kind == "built_in"
    assert source.reason is not None
    assert str(_cache_path()) in source.reason


# --- test 3: bytes decoding, not a platform text codec -----------------------------------------


def test_a_cache_with_smart_quote_bytes_is_read():
    """Windows-meaningful: fails if the reader opens the file in text mode with the platform's
    default codec (`charmap` cannot decode this byte) rather than `json.loads(read_bytes())`. On
    Linux CI the default codec is already UTF-8, so this assertion cannot distinguish the two
    readers there -- it is a regression guard for this machine, not a portable proof.
    """
    write_cache([entry("m-a", display_name="M—A “quoted”")])
    codex = get_provider("codex")
    assert codex.models[0].label == "M—A “quoted”"


# --- test 4: malformed shapes each fall back with their own reason ------------------------------


@pytest.mark.parametrize(
    "write",
    [
        lambda path: path.write_text("[]", encoding="utf-8"),
        lambda path: path.write_text("{}", encoding="utf-8"),
        lambda path: write_cache([], path=path),
        lambda path: write_cache([entry("m-a", visibility="hide")], path=path),
    ],
    ids=["json-array", "empty-object", "zero-models", "only-hidden"],
)
def test_a_malformed_or_empty_cache_falls_back_with_a_reason(write):
    write(_cache_path())
    codex = get_provider("codex")
    assert [m.id for m in codex.models] == [m.id for m in CATALOG["codex"].models]
    assert codex_catalog_source().kind == "built_in"
    assert codex_catalog_source().reason is not None


# --- test 5: a rewrite (new mtime) is reflected with no reload -----------------------------------


def test_a_rewritten_cache_is_reflected_on_the_next_call():
    path = write_cache([entry("m-a")])
    assert [m.id for m in get_provider("codex").models] == ["m-a"]
    before = path.stat()
    write_cache([entry("m-b")])
    # Force the mtime a full millisecond forward: this filesystem's timestamp resolution
    # rounds a 1ns nudge away entirely, which would otherwise leave the memo key
    # (mtime_ns, size) unchanged for two same-length files and mask the very reload this
    # test checks for.
    forced_ns = before.st_mtime_ns + 1_000_000
    os.utime(path, ns=(forced_ns, forced_ns))
    assert [m.id for m in get_provider("codex").models] == ["m-b"]


# --- test 5b: a failed read is never memoised -----------------------------------------------------


def test_a_failed_reading_is_retried_not_stuck_on_the_fallback():
    path = _cache_path()
    path.write_text("{not valid json", encoding="utf-8")
    stat = path.stat()

    codex = get_provider("codex")
    assert [m.id for m in codex.models] == [m.id for m in CATALOG["codex"].models]

    write_cache([entry("m-a")])
    # Force the completed file's mtime back to the truncated file's value, with a different
    # size -- a memo keyed on mtime alone (or one that stores a failed reading) would stay on
    # the fallback here.
    os.utime(path, ns=(stat.st_mtime_ns, stat.st_mtime_ns))

    assert [m.id for m in get_provider("codex").models] == ["m-a"]


# --- test 5c: window lookups fall back to the literal; validation and the offered list do not ----


def test_window_lookups_fall_back_but_the_offered_list_and_validation_do_not():
    write_cache([entry("m-a")])

    # gpt-5.5 is only in the literal, not in this cache -- but its window is still known.
    assert (
        model_context_window("codex", "gpt-5.5") == CATALOG["codex"].model("gpt-5.5").context_window
    )
    assert context_window_for_model("gpt-5.5") == CATALOG["codex"].model("gpt-5.5").context_window

    # The offered list and validation never fall back: gpt-5.5 is refused where it is newly set.
    assert get_provider("codex").model("gpt-5.5") is None


@pytest.mark.asyncio
async def test_post_runners_refuses_a_literal_only_model_when_a_cache_is_present(app, auth_headers):
    write_cache([entry("m-a")])
    response = await app.post(
        P + "/runners",
        json={"name": "r-literal-only", "cli": "codex", "model": "gpt-5.5"},
        headers=auth_headers,
    )
    assert response.status_code == 400, response.text


# --- test 6: through the route -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_runners_accepts_a_cache_listed_model_and_refuses_a_literal_only_one(
    app, auth_headers
):
    write_cache([entry("m-a")])

    accepted = await app.post(
        P + "/runners",
        json={"name": "r-cache-listed", "cli": "codex", "model": "m-a"},
        headers=auth_headers,
    )
    assert accepted.status_code == 201, accepted.text

    refused = await app.post(
        P + "/runners",
        json={"name": "r-cache-gone", "cli": "codex", "model": "gpt-6-sol"},
        headers=auth_headers,
    )
    assert refused.status_code == 400, refused.text


# --- test 7: GET /model-catalog reports source, in priority order --------------------------------


@pytest.mark.asyncio
async def test_get_model_catalog_reports_cli_cache_source_in_priority_order(app, auth_headers):
    write_cache([entry("m-b", priority=2), entry("m-a", priority=1)], client_version="0.156.1")
    response = await app.get("/api/v1/model-catalog", headers=auth_headers)
    body = response.json()

    claude = next(p for p in body["providers"] if p["provider"] == "claude")
    assert claude["source"]["kind"] == "built_in"
    assert claude["source"]["reason"] is None

    codex = next(p for p in body["providers"] if p["provider"] == "codex")
    assert codex["source"]["kind"] == "cli_cache"
    assert codex["source"]["client_version"] == "0.156.1"
    assert [m["id"] for m in codex["models"]] == ["m-a", "m-b"]


@pytest.mark.asyncio
async def test_get_model_catalog_reports_built_in_source_with_no_cache(app, auth_headers):
    response = await app.get("/api/v1/model-catalog", headers=auth_headers)
    body = response.json()
    codex = next(p for p in body["providers"] if p["provider"] == "codex")
    assert codex["source"]["kind"] == "built_in"
    assert codex["source"]["reason"] is not None


# --- test 8: the conftest guard itself ------------------------------------------------------------


def test_with_no_cache_the_effective_catalog_is_exactly_the_literal():
    assert [m.id for m in get_provider("codex").models] == [m.id for m in CATALOG["codex"].models]
