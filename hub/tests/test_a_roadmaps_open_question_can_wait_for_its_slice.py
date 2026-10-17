"""A roadmap's open question can wait for the slice that answers it (F573, the carrying half).

A question naming a slice raises no gap on the roadmap; the slice's change document is asked to
restate it among its own open questions, where it is answered.
"""

from .test_a_roadmap_shows_which_of_its_slices_are_done import (
    BASE,
    ROADMAP,
    ROADMAP_PAYLOAD,
    _approve,
    _change,
    _write,
)

QUESTION = "Is the map rendered into every turn?"
SLICE_DOC = "spec/changes/the-second-slice/spec.json"


def _roadmap(questions):
    return {**ROADMAP_PAYLOAD, "open_questions": questions}


async def test_a_sliced_question_waits_and_an_unsliced_one_still_warns(app, auth_headers, tmp_path):
    await _write(
        app,
        auth_headers,
        ROADMAP,
        "The roadmap",
        _roadmap(
            [
                {"question": QUESTION, "slice": "second"},
                {"question": "Which theme ships first?"},
            ]
        ),
        kind="roadmap",
    )
    refused = await _approve(app, auth_headers, ROADMAP, anyway=False)
    assert refused.status_code == 409, refused.text
    assert refused.text.count("unresolved_question") == 1
    assert "open_questions[1]" in refused.text and "open_questions[0]" not in refused.text


async def test_a_question_naming_an_unknown_slice_is_a_gap(app, auth_headers, tmp_path):
    await _write(
        app,
        auth_headers,
        ROADMAP,
        "The roadmap",
        _roadmap([{"question": QUESTION, "slice": "third"}]),
        kind="roadmap",
    )
    refused = await _approve(app, auth_headers, ROADMAP, anyway=False)
    assert "question_slice_unknown" in refused.text and "third" in refused.text


async def test_the_slice_document_is_asked_to_carry_it_until_it_does(app, auth_headers, tmp_path):
    await _write(
        app,
        auth_headers,
        ROADMAP,
        "The roadmap",
        _roadmap([{"question": QUESTION, "slice": "second"}]),
        kind="roadmap",
    )
    assert (await _approve(app, auth_headers, ROADMAP)).status_code == 200
    link = {"document": ROADMAP, "slice": "second"}
    await _write(
        app, auth_headers, SLICE_DOC, "The second slice", _change("The second slice", link)
    )
    first = await _approve(app, auth_headers, SLICE_DOC, anyway=False)
    assert first.status_code == 409, first.text
    assert "roadmap_question_for_slice" in first.text and QUESTION in first.text

    carried = _change("The second slice", link)
    carried["open_questions"] = [{"question": QUESTION.lower() + " ", "resolved": True}]
    rewritten = await app.put(
        f"{BASE}/documents/{SLICE_DOC}/content", json={"document": carried}, headers=auth_headers
    )
    assert rewritten.status_code == 200, rewritten.text
    second = await _approve(app, auth_headers, SLICE_DOC, anyway=False)
    assert "roadmap_question_for_slice" not in second.text
