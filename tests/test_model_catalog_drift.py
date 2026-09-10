"""The gate for `scripts/check_model_catalog.py`.

That script compares the Hub's committed Codex model catalog against the CLI's own
`~/.codex/models_cache.json`, and its whole value is that it *fires*. Its failure mode is going
quiet: a reduction that returns an empty view agrees with everything, and a reader that skips
every cache entry reports a clean catalog -- which reads like good news and is how a phantom
default model sat in the catalog for four weeks (F267, F174).

**The fixtures are synthetic**, for a reason stronger than `test_openspec_collisions.py`'s: the
cache is *per-machine* and absent in CI, and the catalog literal is edited whenever upstream
moves, so a test asserting either side's contents would be red on every other machine and
green only until the next reconciliation.

The one exception is `test_the_real_catalog_loads_and_reduces_to_a_usable_view`, a structural
invariant with no dependence on which models are declared: the real module must load by path
and reduce to a non-empty view with exactly one default. That is the going-quiet failure,
checked against the only module that can actually exhibit it -- and it is also what covers the
frozen-dataclass import trap, which no synthetic fixture here reproduces.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_model_catalog.py"
REAL_CATALOG = REPO_ROOT / "hub" / "hub" / "model_catalog.py"


def _load():
    """Import the script by path -- `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("check_model_catalog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cmc = _load()

EFFORTS = ("low", "medium", "high", "xhigh")


def catalog_view(models, default_model="a", efforts=EFFORTS, effort_default="medium"):
    return cmc.CatalogView(
        models=tuple(models),
        default_model=default_model,
        effort_values=tuple(efforts),
        effort_default=effort_default,
    )


def cache_view(models, levels=None):
    """A cache view whose models all declare the same reasoning levels unless told otherwise."""
    models = tuple(models)
    if levels is None:
        levels = {m.id: EFFORTS for m in models}
    return cmc.CacheView(
        models=models,
        reasoning_levels=levels,
        fetched_at="2026-09-10T00:00:00Z",
        client_version="0.146.0",
    )


def model(model_id, label=None, window=272_000):
    return cmc.ModelView(model_id, label if label is not None else model_id.upper(), window)


def kinds(drifts):
    return [d.kind for d in drifts]


def write_cache_file(path: Path, models, visibility="list", levels=EFFORTS) -> Path:
    """A `models_cache.json` in the shape the Codex CLI actually writes."""
    path.write_text(
        json.dumps(
            {
                "fetched_at": "2026-09-10T00:00:00Z",
                "etag": 'W/"deadbeef"',
                "client_version": "0.146.0",
                "models": [
                    {
                        "slug": m.id,
                        "display_name": m.label,
                        "context_window": m.context_window,
                        "visibility": visibility,
                        "supported_reasoning_levels": [{"effort": e} for e in levels],
                    }
                    for m in models
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


SYNTHETIC_CATALOG = '''
"""A stand-in for hub/hub/model_catalog.py, duck-typed to what read_catalog reads."""


class _Model:
    def __init__(self, id, label, context_window, default=False):
        self.id = id
        self.label = label
        self.context_window = context_window
        self.default = default


class _Value:
    def __init__(self, id):
        self.id = id


class _Control:
    def __init__(self, id, values, default):
        self.id = id
        self.values = tuple(_Value(v) for v in values)
        self.default = default


class _Provider:
    def __init__(self, models, controls):
        self.models = tuple(models)
        self._controls = {c.id: c for c in controls}

    def control(self, control_id):
        return self._controls.get(control_id)


CATALOG = {
    "codex": _Provider(
        models=[
            _Model("keeper", "KEEPER", 272000, default=True),
            _Model("goner", "GONER", 272000),
        ],
        controls=[_Control("effort", ("low", "medium", "high", "xhigh"), "medium")],
    )
}
'''


def write_catalog_file(path: Path, body: str = SYNTHETIC_CATALOG) -> Path:
    path.write_text(body.strip("\n") + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------- the real module, structurally


def test_the_real_catalog_loads_and_reduces_to_a_usable_view():
    """Content-independent: the module loads by path and the reduction is not empty.

    An empty reduction is the going-quiet failure -- it agrees with every cache. This also
    exercises the frozen-dataclass import path, which needs the module registered in
    `sys.modules` before execution and which no synthetic fixture in this file reproduces.
    """
    view = cmc.read_catalog(REAL_CATALOG)
    assert view.models, "the real catalog reduced to zero codex models"
    assert view.default_model is not None, "the real catalog declares no single default model"
    assert view.default_model in {m.id for m in view.models}
    assert view.effort_values, "the real catalog's effort control reduced to no values"
    assert view.effort_default in view.effort_values


def test_a_catalog_module_with_no_provider_entry_is_an_error():
    view = cmc.read_catalog(REAL_CATALOG, provider="codex")
    assert view.models
    try:
        cmc.read_catalog(REAL_CATALOG, provider="not-a-provider")
    except cmc.CatalogError as exc:
        assert "not-a-provider" in str(exc)
    else:  # pragma: no cover - the assertion below states the failure
        raise AssertionError("an unknown provider did not raise CatalogError")


def test_a_missing_catalog_module_is_an_error_not_an_empty_view(tmp_path):
    try:
        cmc.read_catalog(tmp_path / "absent.py")
    except cmc.CatalogError as exc:
        assert "absent.py" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a missing catalog module did not raise CatalogError")


# ------------------------------------------------------------------------------ read_cache


def test_read_cache_keeps_only_listed_models(tmp_path):
    path = tmp_path / "cache.json"
    payload = {
        "fetched_at": "x",
        "client_version": "y",
        "models": [
            {
                "slug": "shown",
                "display_name": "Shown",
                "context_window": 272000,
                "visibility": "list",
                "supported_reasoning_levels": [{"effort": "low"}],
            },
            {
                "slug": "internal",
                "display_name": "Internal",
                "context_window": 272000,
                "visibility": "hide",
                "supported_reasoning_levels": [{"effort": "low"}],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    view = cmc.read_cache(path)
    assert [m.id for m in view.models] == ["shown"]
    assert "internal" not in view.reasoning_levels


def test_read_cache_rejects_json_that_is_not_a_model_cache(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"something": "else"}), encoding="utf-8")
    try:
        cmc.read_cache(path)
    except cmc.CatalogError as exc:
        assert "models" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a cache with no models list did not raise CatalogError")


# ------------------------------------------------------------------------------- comparison


def test_agreeing_sides_produce_no_drift():
    models = [model("a"), model("b")]
    assert cmc.compare(catalog_view(models), cache_view(models)) == []


def test_a_model_the_catalog_offers_and_upstream_dropped_is_reported():
    drifts = cmc.compare(catalog_view([model("a"), model("gone")]), cache_view([model("a")]))
    assert kinds(drifts) == ["declared but gone"]
    assert "gone" in drifts[0].detail


def test_a_model_upstream_offers_and_the_catalog_lacks_is_reported():
    drifts = cmc.compare(catalog_view([model("a")]), cache_view([model("a"), model("brand-new")]))
    assert kinds(drifts) == ["listed but undeclared"]
    assert "brand-new" in drifts[0].detail


def test_a_withdrawn_model_is_reported_once_not_also_for_its_fields():
    """The membership check runs first so a gone model does not also accrue field drift."""
    drifts = cmc.compare(
        catalog_view([model("a"), model("gone", label="Old", window=1)]),
        cache_view([model("a")]),
    )
    assert kinds(drifts) == ["declared but gone"]


def test_a_context_window_that_disagrees_is_reported():
    drifts = cmc.compare(
        catalog_view([model("a", window=272_000)]), cache_view([model("a", window=400_000)])
    )
    assert kinds(drifts) == ["context window"]
    assert "272000" in drifts[0].detail and "400000" in drifts[0].detail


def test_a_label_that_disagrees_is_reported():
    drifts = cmc.compare(
        catalog_view([model("a", label="Old Name")]), cache_view([model("a", label="New Name")])
    )
    assert kinds(drifts) == ["label"]


def test_the_default_model_no_longer_listed_upstream_is_reported():
    drifts = cmc.compare(
        catalog_view([model("a"), model("phantom")], default_model="phantom"),
        cache_view([model("a")]),
    )
    assert kinds(drifts) == ["default model", "declared but gone"]


def test_a_catalog_with_no_single_default_is_reported():
    models = [model("a")]
    drifts = cmc.compare(catalog_view(models, default_model=None), cache_view(models))
    assert kinds(drifts) == ["default model"]


def test_effort_values_are_the_intersection_not_the_union():
    models = [model("a"), model("b")]
    levels = {
        "a": ("low", "medium", "high", "xhigh", "ultra"),
        "b": ("low", "medium", "high", "xhigh"),
    }
    view = cache_view(models, levels)
    assert view.effort_intersection() == ("low", "medium", "high", "xhigh")
    assert cmc.compare(catalog_view(models), view) == []


def test_effort_intersection_keeps_declaration_order_not_alphabetical_order():
    models = [model("a")]
    view = cache_view(models, {"a": ("low", "medium", "high", "xhigh")})
    assert view.effort_intersection() == ("low", "medium", "high", "xhigh")


def test_a_catalog_offering_a_value_one_model_rejects_is_reported():
    models = [model("a"), model("b")]
    levels = {"a": ("low", "medium", "high", "xhigh"), "b": ("low", "medium", "high")}
    drifts = cmc.compare(catalog_view(models), cache_view(models, levels))
    assert kinds(drifts) == ["effort values"]
    assert "xhigh" in drifts[0].detail


def test_an_effort_default_outside_the_offered_values_is_reported():
    models = [model("a")]
    drifts = cmc.compare(
        catalog_view(models, efforts=("low", "high"), effort_default="medium"),
        cache_view(models, {"a": ("low", "high")}),
    )
    assert kinds(drifts) == ["effort default"]


def test_a_cache_listing_nothing_does_not_accuse_the_effort_control():
    """An empty cache says nothing about the intersection; claiming drift there is a false alarm."""
    drifts = cmc.compare(catalog_view([model("a")]), cache_view([], levels={}))
    assert "effort values" not in kinds(drifts)


# ------------------------------------------------------------------------- report and main


def test_report_writes_to_the_stream_it_is_given(tmp_path):
    """The import-time-stdout trap: a default argument would send this to the real stdout."""

    class Sink:
        def __init__(self):
            self.text = ""

        def write(self, chunk):
            self.text += chunk

        def flush(self):
            pass

    sink = Sink()
    models = [model("a")]
    drifts = cmc.compare(catalog_view([model("a"), model("gone")]), cache_view(models))
    cmc.report(drifts, catalog_view(models), cache_view(models), Path("c.py"), Path("k.json"), sink)
    assert "declared but gone" in sink.text
    assert "gone" in sink.text


def test_main_exits_one_and_names_the_drift(tmp_path, capsys):
    catalog = write_catalog_file(tmp_path / "cat.py")
    cache = write_cache_file(tmp_path / "cache.json", [model("keeper", "KEEPER")])
    code = cmc.main(["--catalog", str(catalog), "--cache", str(cache)])
    out = capsys.readouterr().out
    assert code == 1
    assert "goner" in out


def test_main_exits_zero_when_the_two_agree(tmp_path, capsys):
    catalog = write_catalog_file(tmp_path / "cat.py")
    cache = write_cache_file(
        tmp_path / "cache.json", [model("keeper", "KEEPER"), model("goner", "GONER")]
    )
    code = cmc.main(["--catalog", str(catalog), "--cache", str(cache)])
    out = capsys.readouterr().out
    assert code == 0
    assert "agrees with the cache" in out


def test_main_skips_rather_than_fails_when_no_cache_exists(tmp_path, capsys):
    """The CI-absent case, and the whole reason this is a script rather than a gate."""
    catalog = write_catalog_file(tmp_path / "cat.py")
    code = cmc.main(["--catalog", str(catalog), "--cache", str(tmp_path / "absent.json")])
    out = capsys.readouterr().out
    assert code == 0
    assert "SKIPPED" in out


def test_main_exits_two_when_the_cache_is_present_but_unreadable(tmp_path, capsys):
    """A corrupt cache must not read as a skip -- that would bless a drifted catalog."""
    catalog = write_catalog_file(tmp_path / "cat.py")
    cache = tmp_path / "cache.json"
    cache.write_text("{ not json", encoding="utf-8")
    code = cmc.main(["--catalog", str(catalog), "--cache", str(cache)])
    err = capsys.readouterr().err
    assert code == 2
    assert "did not parse" in err
