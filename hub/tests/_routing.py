"""Enumerate an app's real routes, whatever shape the framework keeps them in.

Two tests read the routing table rather than trusting a docstring: `test_mcp_body_contract` checks
that every tool's body is actually accepted by the route it posts to, and `test_spec_documents_api`
checks that no route anywhere can mutate a spec document event. Both were written against a
FastAPI/Starlette that flattened `include_router` into `app.routes` as `APIRoute` objects carrying
their **full** path.

Starlette 1.x does not. `app.routes` now holds `_IncludedRouter` wrappers, the real `APIRoute`s sit
inside them — nested, because routers include routers — and each inner route's `.path` is
**relative**, with the prefix applied by the wrapper at match time. So the old code found no routes
at all and both tests failed with "no such route", which reads like a missing endpoint rather than
a changed data structure.

This walks either shape and returns the full path with the route, so a caller can match on the path
a real request would use. On the older layout there are no wrappers, the accumulated prefix stays
empty, and it degrades to iterating `app.routes`.

Deliberately duck-typed rather than importing `_IncludedRouter`: the name is private and exists only
on the newer versions, so importing it would make this module the thing that breaks next.
"""

from __future__ import annotations

from typing import Iterator, List, Tuple

from fastapi.routing import APIRoute


def _child_router(route: object):
    """The router a wrapper stands in for, or None if this is an ordinary route."""
    return getattr(route, "original_router", None)


def iter_api_routes(app, _routes=None, _prefix: str = "") -> Iterator[Tuple[str, APIRoute]]:
    """Yield `(full_path, route)` for every `APIRoute` reachable from *app*.

    `full_path` is what a client would request: the accumulated prefixes plus the route's own path.

    Only **strict ancestors** contribute to the accumulated prefix. A route sitting directly inside
    a router already carries that router's own prefix in its `.path`, so adding it again produces
    `/api/v1/agent-actions/agent-actions/messages` — which is what the first two attempts at this
    did, in two different ways, before the shape was traced rather than assumed.
    """
    routes = app.routes if _routes is None else _routes
    for route in routes:
        child = _child_router(route)
        if child is None:
            if isinstance(route, APIRoute):
                yield _prefix + route.path, route
            continue
        # Descend. This router's own routes keep `_prefix` — their `.path` already includes its
        # prefix — while routers nested inside it need `_prefix` plus this one's contribution.
        own = getattr(child, "prefix", "")
        for inner in getattr(child, "routes", []):
            if _child_router(inner) is not None:
                yield from iter_api_routes(app, [inner], _prefix + own)
            elif isinstance(inner, APIRoute):
                yield _prefix + inner.path, inner


def api_route_paths(app) -> List[str]:
    """Every full path in the app, for tests that only care that something is absent."""
    return [path for path, _ in iter_api_routes(app)]
