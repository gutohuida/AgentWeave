"""Compare the Hub's committed Codex model catalog against the CLI's own model cache.

**Why this exists.** `hub/hub/model_catalog.py`'s docstring names `~/.codex/models_cache.json`
as the source of truth for the Codex half of the catalog -- *"read directly from
`~/.codex/models_cache.json`, the CLI's own server-synced catalog"* -- but the catalog is a
**compile-time literal**, hand-copied once, and **nothing re-reads that file**. A model can be
withdrawn upstream, or a new one offered, and the catalog goes on declaring the old list. That
is how a phantom default model sat in the catalog for four weeks (F267, F174).

**Why a script and not a test.** The cache is per-machine and absent in CI, so a test could
only skip there -- which is exactly where a green suite would most misleadingly bless a drifted
catalog. This is the shape that gets run when someone suspects the catalog is wrong. Do not
promote it to a CI gate; on a machine with no Codex CLI it has nothing to compare and says so.

**The literal this compares against is now the fallback, not the offered list**
(`the-codex-models-offered-are-the-ones-its-cli-lists`). `hub/hub/model_catalog.py` reads a
Codex model cache at runtime and offers exactly what it lists; the literal `CATALOG["codex"]`
this script diffs is used only when a cache is absent, unreadable, malformed, or lists no model.
So a drift this script reports no longer means the Hub is offering the wrong list -- on any
machine with a readable cache, it already is not. It means the *fallback* has drifted from what
some installed CLI was offered, which still matters for CI, a machine with no Codex CLI, and a
Docker Hub whose container has no Codex home.

**What it compares**, all of it derived from rules `model_catalog.py`'s own docstring states:

| check | the rule it enforces |
|---|---|
| declared but gone | every model the catalog offers still exists upstream with `visibility: "list"` |
| listed but undeclared | every model the provider lists is reachable through the catalog |
| context window | *"the context window it actually has, never a substitute"* -- catalog vs the cache's `context_window` |
| label | the catalog's label is the cache's `display_name` |
| default model | the catalog's `default=True` model is one the cache still lists |
| effort values | the effort control is *"the INTERSECTION of every listed model's `supported_reasoning_levels`"* |
| effort default | the control's default is one of the values it offers |

`visibility: "hide"` entries are excluded on both sides, per the docstring: `codex-auto-review`
is an internal review model, not one an operator selects.

Usage:

    py -3.11 scripts/check_model_catalog.py
    py -3.11 scripts/check_model_catalog.py --cache /tmp/some-cache.json
    py -3.11 scripts/check_model_catalog.py --catalog hub/hub/model_catalog.py

Exit codes: 0 the two agree (or the cache is absent and the check was skipped), 1 something
drifted, 2 the catalog or the cache could not be read.

**`--provider copilot`** (`a-copilot-agent-runs-over-acp`, design D13). Copilot keeps no model
file; its list is printed by `copilot help config` (no model call), so this section runs that
command -- or reads a saved copy with `--help-config FILE` -- and compares model **ids** only:
Copilot prints no labels or windows, and the catalog declares every Copilot window `None`
because Copilot reports it per turn. `auto` is the catalog's own default and is not printed, so it
is left out of the comparison. No `copilot` on PATH and no file given is a skip, as above.

    py -3.11 scripts/check_model_catalog.py --provider copilot
    py -3.11 scripts/check_model_catalog.py --provider copilot --help-config saved.txt
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

#: The only provider with a machine-readable upstream catalog. Claude's models are verified from
#: `claude --help` and live `contextWindow` samples instead -- there is no file to diff.
PROVIDER = "codex"

DEFAULT_CATALOG = Path("hub/hub/model_catalog.py")
DEFAULT_CACHE = Path(os.path.expanduser("~/.codex/models_cache.json"))

#: The catalog control whose values the cache can adjudicate.
EFFORT_CONTROL = "effort"

#: Cache entries with any other visibility are internal, and neither side should carry them.
LISTED = "list"


class ModelView(NamedTuple):
    """One model, reduced to the fields the two sides can be compared on."""

    id: str
    label: str
    context_window: Optional[int]


class CatalogView(NamedTuple):
    models: Tuple[ModelView, ...]
    default_model: Optional[str]
    effort_values: Tuple[str, ...]
    effort_default: Optional[str]


class CacheView(NamedTuple):
    models: Tuple[ModelView, ...]
    #: Per model id, the reasoning levels that model declares -- the raw material of the
    #: intersection rule, kept rather than pre-reduced so the report can name the dissenter.
    reasoning_levels: Dict[str, Tuple[str, ...]]
    fetched_at: Optional[str]
    client_version: Optional[str]

    def effort_intersection(self) -> Tuple[str, ...]:
        """The values every listed model supports, in the order the first model declares them.

        Order comes from a declaration rather than from `sorted()` because the catalog's own
        tuple is written in ascending-effort order (`low, medium, high, xhigh`), and a report
        that alphabetised it would accuse a correct catalog of drifting.
        """
        if not self.reasoning_levels:
            return ()
        ordered = next(iter(self.reasoning_levels.values()))
        shared = set(ordered)
        for levels in self.reasoning_levels.values():
            shared &= set(levels)
        return tuple(value for value in ordered if value in shared)


class Drift(NamedTuple):
    kind: str
    detail: str


class CatalogError(Exception):
    """The catalog or the cache is present but unreadable. Distinct from an absent cache."""


def read_catalog(path: Path, provider: str = PROVIDER) -> CatalogView:
    """Load `model_catalog.py` **by path** and reduce one provider to a comparable view.

    By path, and not `from hub.model_catalog import CATALOG`, for two reasons: this script runs
    from the repo root where a top-level `hub/` shadows the *installed* Hub package (the trap
    CLAUDE.md documents for `python -m uvicorn`), and the module imports nothing outside the
    stdlib, so nothing about it needs the package around it.
    """
    if not path.is_file():
        raise CatalogError(f"no catalog module at {path}")
    spec = importlib.util.spec_from_file_location("_aw_model_catalog_under_check", path)
    if spec is None or spec.loader is None:
        raise CatalogError(f"cannot load {path} as a Python module")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec, and removed after: `@dataclass(frozen=True)` reaches for
    # `sys.modules[cls.__module__].__dict__` while building `__init__`, so a module executed
    # outside `sys.modules` dies with `'NoneType' object has no attribute '__dict__'` -- which
    # would come back from this script as "the catalog did not import" and read like a real
    # defect in the catalog. Measured 2026-09-10.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # a broken catalog is a finding, not something to pass silently
        raise CatalogError(f"{path} did not import: {exc}") from exc
    finally:
        sys.modules.pop(spec.name, None)

    catalog = getattr(module, "CATALOG", None)
    if not isinstance(catalog, dict) or provider not in catalog:
        raise CatalogError(f"{path} declares no CATALOG entry for {provider!r}")
    entry = catalog[provider]

    models = tuple(ModelView(m.id, m.label, m.context_window) for m in entry.models)
    defaults = [m.id for m in entry.models if getattr(m, "default", False)]
    control = entry.control(EFFORT_CONTROL)
    return CatalogView(
        models=models,
        default_model=defaults[0] if len(defaults) == 1 else None,
        effort_values=tuple(v.id for v in control.values) if control is not None else (),
        effort_default=control.default if control is not None else None,
    )


def read_cache(path: Path) -> CacheView:
    """Reduce the CLI's `models_cache.json` to the same shape, listed models only."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"{path} did not parse as JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise CatalogError(f"{path} has no 'models' list -- not a Codex model cache")

    models: List[ModelView] = []
    levels: Dict[str, Tuple[str, ...]] = {}
    for raw in data["models"]:
        if not isinstance(raw, dict) or raw.get("visibility") != LISTED:
            continue
        slug = str(raw.get("slug", ""))
        if not slug:
            continue
        models.append(ModelView(slug, str(raw.get("display_name", "")), raw.get("context_window")))
        levels[slug] = tuple(
            str(level.get("effort"))
            for level in raw.get("supported_reasoning_levels", [])
            if isinstance(level, dict) and level.get("effort")
        )
    return CacheView(
        models=tuple(models),
        reasoning_levels=levels,
        fetched_at=data.get("fetched_at"),
        client_version=data.get("client_version"),
    )


def compare(catalog: CatalogView, cache: CacheView) -> List[Drift]:
    """Every way the committed literal and the cache disagree, worst first.

    Model membership is compared before per-model fields so a withdrawn model is reported once,
    as gone, rather than a second time for a window it no longer has.
    """
    declared = {m.id: m for m in catalog.models}
    listed = {m.id: m for m in cache.models}
    drifts: List[Drift] = []

    if catalog.default_model is None:
        drifts.append(
            Drift("default model", "the catalog declares no single default model for this provider")
        )
    elif catalog.default_model not in listed:
        drifts.append(
            Drift(
                "default model",
                f"the catalog's default {catalog.default_model!r} is not a model the cache lists"
                " -- every run that takes the default asks for a model the CLI does not offer",
            )
        )

    for model_id in sorted(set(declared) - set(listed)):
        drifts.append(
            Drift(
                "declared but gone",
                f"{model_id!r} is offered by the catalog and not listed upstream",
            )
        )
    for model_id in sorted(set(listed) - set(declared)):
        drifts.append(
            Drift(
                "listed but undeclared",
                f"{model_id!r} is listed upstream and unreachable through the catalog",
            )
        )

    for model_id in sorted(set(declared) & set(listed)):
        ours, theirs = declared[model_id], listed[model_id]
        if ours.context_window != theirs.context_window:
            drifts.append(
                Drift(
                    "context window",
                    f"{model_id}: catalog says {ours.context_window}, cache says"
                    f" {theirs.context_window}",
                )
            )
        if theirs.label and ours.label != theirs.label:
            drifts.append(
                Drift(
                    "label",
                    f"{model_id}: catalog says {ours.label!r}, cache says {theirs.label!r}",
                )
            )

    shared = cache.effort_intersection()
    if shared and tuple(catalog.effort_values) != shared:
        drifts.append(
            Drift(
                "effort values",
                f"catalog offers {list(catalog.effort_values)}, the intersection of every listed"
                f" model's supported_reasoning_levels is {list(shared)}",
            )
        )
    if catalog.effort_default is not None and catalog.effort_default not in catalog.effort_values:
        drifts.append(
            Drift(
                "effort default",
                f"the control's default {catalog.effort_default!r} is not one of the values it"
                f" offers {list(catalog.effort_values)}",
            )
        )
    return drifts


def report(
    drifts: Sequence[Drift],
    catalog: CatalogView,
    cache: CacheView,
    catalog_path: Path,
    cache_path: Path,
    stream=None,
) -> None:
    # Resolved at call time, not as a default argument: a default binds the `sys.stdout` that
    # existed at import, so `redirect_stdout` (or pytest's `capsys`) would capture nothing.
    stream = sys.stdout if stream is None else stream
    print(f"catalog: {catalog_path} ({len(catalog.models)} {PROVIDER} model(s))", file=stream)
    print(
        f"cache:   {cache_path} (fetched_at={cache.fetched_at}"
        f" client_version={cache.client_version}, {len(cache.models)} listed)",
        file=stream,
    )
    if not drifts:
        print(
            f"\nThe committed {PROVIDER} catalog agrees with the cache on every field checked.",
            file=stream,
        )
        return

    print(f"\n{len(drifts)} drift(s):", file=stream)
    for drift in drifts:
        print(f"  [{drift.kind}] {drift.detail}", file=stream)
    print(
        "\nThe catalog is a hand-copied literal; the cache is the CLI's server-synced list."
        f"\nReconcile {catalog_path} against it -- and note the cache itself is only as fresh as"
        "\nthe last time the Codex CLI ran on this machine.",
        file=stream,
    )


#: The Copilot catalog's own default, which `copilot help config` does not print.
COPILOT_AUTO = "auto"

_COPILOT_MODEL_ITEM = re.compile(r'^\s+-\s+"([^"]+)"\s*$')


def parse_copilot_models(help_text: str) -> Tuple[str, ...]:
    """The ids listed under `` `model`: `` in `copilot help config`, in the order printed.

    The section runs from the `` `model`: `` line to the next setting's heading, and each id is
    a `    - "<id>"` line. An empty result means the format moved, which the caller reports as
    an error rather than as "every declared model is gone".
    """
    ids: List[str] = []
    in_section = False
    for line in help_text.splitlines():
        if line.strip().startswith("`model`:"):
            in_section = True
            continue
        if not in_section:
            continue
        match = _COPILOT_MODEL_ITEM.match(line)
        if match:
            ids.append(match.group(1))
        elif line.strip().startswith("`"):
            break
    return tuple(ids)


def compare_copilot(catalog: CatalogView, listed: Sequence[str]) -> List[Drift]:
    """Model ids only: Copilot prints no labels or windows to compare."""
    declared = {m.id for m in catalog.models} - {COPILOT_AUTO}
    printed = set(listed)
    drifts: List[Drift] = []
    if catalog.default_model != COPILOT_AUTO:
        drifts.append(
            Drift(
                "default model",
                f"the Copilot default is {catalog.default_model!r}, not {COPILOT_AUTO!r}",
            )
        )
    for model_id in sorted(declared - printed):
        drifts.append(
            Drift(
                "declared but gone",
                f"{model_id!r} is offered by the catalog and not printed by `copilot help config`",
            )
        )
    for model_id in sorted(printed - declared):
        drifts.append(
            Drift(
                "listed but undeclared",
                f"{model_id!r} is printed by `copilot help config` and unreachable through the"
                " catalog",
            )
        )
    return drifts


def _copilot_help_config() -> Optional[str]:
    """`copilot help config`'s output, or None when no `copilot` is on PATH."""
    executable = shutil.which("copilot")
    if executable is None:
        return None
    result = subprocess.run(
        [executable, "help", "config"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise CatalogError(f"`copilot help config` exited {result.returncode}: {result.stderr}")
    return result.stdout


def main_copilot(catalog_path: Path, help_config: Optional[Path]) -> int:
    try:
        if help_config is not None:
            text: Optional[str] = help_config.read_text(encoding="utf-8")
            source = str(help_config)
        else:
            text = _copilot_help_config()
            source = "copilot help config"
        if text is None:
            print(
                "SKIPPED: no `copilot` on PATH and no --help-config file given."
                "\nWith no Copilot CLI there is nothing to compare the catalog against, and that"
                "\nis not a failure."
            )
            return 0
        listed = parse_copilot_models(text)
        if not listed:
            raise CatalogError(f"{source} lists no model under `model`: -- has its format moved?")
        catalog = read_catalog(catalog_path, provider="copilot")
    except (CatalogError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    drifts = compare_copilot(catalog, listed)
    print(f"catalog: {catalog_path} ({len(catalog.models)} copilot model(s), including auto)")
    print(f"source:  {source} ({len(listed)} model(s) printed)")
    if not drifts:
        print("\nThe committed copilot catalog agrees with the CLI's model list.")
        return 0
    print(f"\n{len(drifts)} drift(s):")
    for drift in drifts:
        print(f"  [{drift.kind}] {drift.detail}")
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the Hub's committed Codex model catalog against ~/.codex/models_cache.json."
        ),
        epilog="Not a CI gate: the cache is per-machine, and an absent one is a skip, not a failure.",
    )
    parser.add_argument(
        "--catalog", type=Path, default=DEFAULT_CATALOG, help=f"default: {DEFAULT_CATALOG}"
    )
    parser.add_argument(
        "--cache", type=Path, default=DEFAULT_CACHE, help=f"default: {DEFAULT_CACHE}"
    )
    parser.add_argument(
        "--provider",
        choices=("codex", "copilot"),
        default="codex",
        help="which provider's catalog to check (default: codex)",
    )
    parser.add_argument(
        "--help-config",
        type=Path,
        default=None,
        help="copilot only: a saved `copilot help config` output, instead of running it",
    )
    args = parser.parse_args(argv)

    if args.provider == "copilot":
        return main_copilot(args.catalog, args.help_config)

    cache_path: Path = args.cache
    if not cache_path.is_file():
        # The CI-absent case, and the reason this is a script. Say it loudly and succeed.
        print(
            f"SKIPPED: no Codex model cache at {cache_path}."
            "\nThe cache is written by the Codex CLI on this machine; with no CLI installed there"
            "\nis nothing to compare the catalog against, and that is not a failure."
        )
        return 0

    try:
        catalog = read_catalog(args.catalog)
        cache = read_cache(cache_path)
    except CatalogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    drifts = compare(catalog, cache)
    report(drifts, catalog, cache, args.catalog, cache_path)
    return 1 if drifts else 0


if __name__ == "__main__":
    raise SystemExit(main())
