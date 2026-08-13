"""A specification turn says so beside the operator's message, not only in system context.

Change `2026-08-13-the-hubs-procedure-outranks-an-installed-one`, section 7. That change stated
precedence in the canonical context and said plainly that if it lost again the answer would not be
more wording. It lost again.

Three live runs had the phase block, the precedence statement, the conversational-interview floor
and `submit_spec_document` in the tool list — all verified present in the delivered context file —
and the agent announced *"I'll use the OpenSpec exploration workflow"*, ran the questionnaire the
floor had just told it not to run, and when its questions went unanswered invented the answers.

What an agent weighs against the request is what arrives with the request. A skill description is
matched against the operator's sentence; standing context is read once, before that sentence
existed. So the directive moves into the same channel.
"""

from hub.launchability import spec_turn_notice


def test_an_ordinary_turn_carries_nothing():
    """No document open, no notice. The prompt is the operator's message and the access path."""
    assert spec_turn_notice(None) is None
    assert spec_turn_notice("") is None


def test_the_notice_overrides_another_workflow_in_the_prompt_itself():
    notice = spec_turn_notice("exploring")
    assert "SPECIFICATION TURN" in notice
    assert "overrides any other specification workflow" in notice
    # Names no product, for the same reason the floor does not: a blocklist dates the moment a
    # different tool is installed.
    assert "openspec" not in notice.lower()


def test_exploring_asks_for_the_interview_in_the_reply():
    notice = spec_turn_notice("exploring")
    assert "THIS REPLY" in notice
    assert "stop and let the operator answer" in notice


def test_exploring_forbids_answering_its_own_questions():
    """The specific failure of loop iteration 2: the agent asked, got nothing back, and proceeded
    on invented assumptions rather than stopping. A prose question does not block the way the tool
    does, so the stop has to be stated."""
    notice = spec_turn_notice("exploring")
    assert "Do not answer your own questions" in notice
    assert "guessed requirement" in notice


def test_every_phase_names_the_only_way_to_write():
    for phase in ("exploring", "proposed", "approved"):
        assert "submit_spec_document" in spec_turn_notice(phase)


def test_a_later_phase_does_not_ask_for_an_interview():
    """Interviewing is the exploring duty. Carrying it into `approved` would tell an agent that is
    supposed to be implementing to go back and ask questions."""
    notice = spec_turn_notice("approved")
    assert "THIS REPLY" not in notice
    assert "submit_spec_document" in notice


def test_exploring_is_told_to_name_the_document():
    """The rename is an action taken on information acquired during a
    particular turn, which is why it is stated with the turn."""
    notice = spec_turn_notice("exploring")
    assert "rename_spec_document" in notice
    assert "placeholder" in notice.lower()


def test_a_later_phase_is_not_told_to_name_the_document():
    """A proposed or approved document has already been named."""
    for phase in ("proposed", "approved"):
        assert "rename_spec_document" not in spec_turn_notice(phase)
