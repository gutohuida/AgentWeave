"""The Hub searches inside the vault's documents (`a-vault-page-that-says-what-it-holds` FR-9).

`GET /vault/search?q=` answers each source agents can read whose text holds the query, ignoring
case, with how many lines match and the first three. Archived sources and private text held on
another machine are left out.
"""

import time

import pytest

from .test_vault import BASE, _foreign_stub, _upload

TEXT = "Intro.\nSecond.\nThird.\nRefund one.\n5\n6\n7\n8\nrefund two.\nx\ny\nREFUND three.\n"


async def _search(app, auth_headers, q: str):
    return await app.get(f"{BASE}/vault/search", params={"q": q}, headers=auth_headers)


@pytest.mark.asyncio
async def test_text_route_answers(app, auth_headers, tmp_path) -> None:
    tracked = await _upload(app, auth_headers, name="Tracked", content=TEXT)
    archived = await _upload(app, auth_headers, name="Old", content="a\nrefund\n")
    gone = await app.post(f"{BASE}/vault/sources/{archived['id']}/archive", headers=auth_headers)
    assert gone.status_code == 200, gone.text
    _foreign_stub(tmp_path)  # private, text held on another machine

    answered = await _search(app, auth_headers, "REFUND")
    assert answered.status_code == 200, answered.text
    hits = answered.json()["hits"]
    assert [h["source"] for h in hits] == [tracked["id"]]
    assert hits[0]["total"] == 3
    assert hits[0]["lines"] == [
        {"line": 4, "text": "Refund one."},
        {"line": 9, "text": "refund two."},
        {"line": 12, "text": "REFUND three."},
    ]

    short = await _search(app, auth_headers, "r")
    assert short.status_code == 400
    assert "2 characters" in short.json()["detail"]


@pytest.mark.asyncio
async def test_only_the_first_three_lines_are_kept(app, auth_headers) -> None:
    await _upload(app, auth_headers, content="refund\n" * 5)
    hit = (await _search(app, auth_headers, "refund")).json()["hits"][0]
    assert hit["total"] == 5
    assert [line["line"] for line in hit["lines"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_search_over_a_vault_of_this_size_is_fast(app, auth_headers, tmp_path) -> None:
    for index in range(104):
        await _upload(app, auth_headers, name=f"S{index}", content=("lorem ipsum dolor\n" * 2400))
    await _search(app, auth_headers, "lorem")  # the first read of freshly written files is cold
    started = time.perf_counter()
    answered = await _search(app, auth_headers, "refund")
    assert answered.status_code == 200
    assert time.perf_counter() - started < 1.0


@pytest.mark.asyncio
async def test_a_match_past_the_first_300_characters_stays_in_the_line(app, auth_headers) -> None:
    # VPTSW-7: the route cut each line to its first 300 characters, so on a long line whose match
    # sat at character 516 the text the UI marks held no match at all.
    line = (
        ("After the same re-distil, the fact that stood " * 11)
        + "the approved refund-limits change"
        + " tail" * 40
    )
    assert line.index("refund") > 300
    await _upload(app, auth_headers, content=f"first\n{line}\n")
    hit = (await _search(app, auth_headers, "refund")).json()["hits"][0]
    text = hit["lines"][0]["text"]
    assert hit["lines"][0]["line"] == 2
    assert "refund" in text
    assert len(text) <= 300
