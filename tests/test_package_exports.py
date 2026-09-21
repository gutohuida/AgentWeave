"""Every name a module's `__all__` promises must exist.

`agentweave.templates.__all__` once named `SKILL_REFERENCES_DIR`, which nothing defined, so
`from agentweave.templates import *` raised `AttributeError` in the published package (F404).
Walking the whole package guards every module, not only the one that broke.
"""

import importlib
import pkgutil

import agentweave


def _modules():
    yield "agentweave"
    for info in pkgutil.walk_packages(agentweave.__path__, "agentweave."):
        yield info.name


def test_every_all_entry_is_defined():
    missing = []
    for name in _modules():
        module = importlib.import_module(name)
        for exported in getattr(module, "__all__", []):
            if not hasattr(module, exported):
                missing.append(f"{name}.{exported}")
    assert missing == []


def test_star_import_of_templates_succeeds():
    namespace: dict = {}
    exec("from agentweave.templates import *", namespace)
    assert "get_template" in namespace
