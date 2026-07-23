"""Tests for spec storage endpoints."""

import pytest

BASE = "/api/v1/project"


@pytest.mark.asyncio
async def test_sync_list_get_round_trip(app, auth_headers):
    resp = await app.post(
        f"{BASE}/specs/sync",
        json={"path": "spec/spec.html", "content": "<html><body>v1</body></html>"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["path"] == "spec/spec.html"
    assert resp.json()["updated_at"]

    list_resp = await app.get(f"{BASE}/specs", headers=auth_headers)
    assert list_resp.status_code == 200
    specs = list_resp.json()["specs"]
    assert len(specs) == 1
    assert specs[0]["path"] == "spec/spec.html"
    assert specs[0]["updated_at"]

    get_resp = await app.get(f"{BASE}/spec", params={"path": "spec/spec.html"}, headers=auth_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["path"] == "spec/spec.html"
    assert data["content"] == "<html><body>v1</body></html>"
    assert data["updated_at"]


@pytest.mark.asyncio
async def test_sync_upsert_overwrites_content_and_updates_timestamp(app, auth_headers):
    resp1 = await app.post(
        f"{BASE}/specs/sync",
        json={"path": "spec/spec.html", "content": "<html>old</html>"},
        headers=auth_headers,
    )
    assert resp1.status_code == 200
    first_updated = resp1.json()["updated_at"]

    resp2 = await app.post(
        f"{BASE}/specs/sync",
        json={"path": "spec/spec.html", "content": "<html>new</html>"},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["updated_at"] >= first_updated

    get_resp = await app.get(f"{BASE}/spec", params={"path": "spec/spec.html"}, headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["content"] == "<html>new</html>"

    # Still a single spec row — upsert, not insert.
    list_resp = await app.get(f"{BASE}/specs", headers=auth_headers)
    assert len(list_resp.json()["specs"]) == 1


@pytest.mark.asyncio
async def test_sync_rejects_invalid_paths(app, auth_headers):
    for bad in ["../etc", "spec/foo.txt", "foo/spec.html"]:
        resp = await app.post(
            f"{BASE}/specs/sync",
            json={"path": bad, "content": "<html></html>"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, f"expected 422 for path={bad!r}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_sync_accepts_change_spec_paths(app, auth_headers):
    resp = await app.post(
        f"{BASE}/specs/sync",
        json={"path": "spec/changes/add-login/spec.html", "content": "<html>c</html>"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_unknown_spec_returns_404(app, auth_headers):
    # The test DB is shared across tests, so use a path no other test syncs.
    resp = await app.get(
        f"{BASE}/spec",
        params={"path": "spec/changes/never-synced/spec.html"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_ordering_puts_main_spec_first(app, auth_headers):
    mine = [
        "spec/changes/zzz-change/spec.html",
        "spec/changes/aaa-change/spec.html",
        "spec/spec.html",
    ]
    for path in mine:
        resp = await app.post(
            f"{BASE}/specs/sync",
            json={"path": path, "content": "<html></html>"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    list_resp = await app.get(f"{BASE}/specs", headers=auth_headers)
    paths = [s["path"] for s in list_resp.json()["specs"]]
    # Main spec first overall, then change specs sorted by path (filter out
    # rows synced by other tests — the test DB is shared).
    assert paths[0] == "spec/spec.html"
    assert [p for p in paths if p in mine] == [
        "spec/spec.html",
        "spec/changes/aaa-change/spec.html",
        "spec/changes/zzz-change/spec.html",
    ]


@pytest.mark.asyncio
async def test_sync_rejects_oversized_content(app, auth_headers):
    resp = await app.post(
        f"{BASE}/specs/sync",
        json={"path": "spec/spec.html", "content": "x" * (2 * 1024 * 1024 + 1)},
        headers=auth_headers,
    )
    assert resp.status_code == 413
