"""The Hub version must come from packaging metadata, not a hardcoded literal.

`hub/hub/__init__.py` and the FastAPI app used to carry a hardcoded "0.1.0"
while hub/pyproject.toml had moved on many releases, so the version advertised
in the OpenAPI schema was wrong for anyone reading /docs.
"""

import hub
from hub.main import create_app


def test_package_version_is_not_hardcoded_stale_literal():
    """__version__ must resolve from metadata, never the old "0.1.0" literal."""
    assert hub.__version__ != "0.1.0", (
        "hub.__version__ is the stale hardcoded literal; it should be read from "
        "installed package metadata"
    )


def test_app_version_matches_package_version():
    """The OpenAPI version must be whatever the package reports, not a literal."""
    app = create_app()
    assert app.version == hub.__version__
