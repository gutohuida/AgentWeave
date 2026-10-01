"""Per-runner-CLI adapters (design `each-runner-cli-is-one-adapter`, D1).

The package's own table — `ADAPTERS`, `get_adapter`, `build_command`, `resolve_access_axes` — is
built up as `claude.py` and `codex.py` land (tasks 2.2/2.3); this file stays empty until then so
that importing it now cannot pull in a half-built adapter.

Nothing in this package may import `hub.db`, `hub.worker`, `hub.launchability` or `hub.api` (D1):
a run's command line has to be buildable without a database connection.
"""

from __future__ import annotations
