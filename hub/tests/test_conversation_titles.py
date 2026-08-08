"""A conversation is named by its first message, and the operator's name for it wins.

The rule the whole change rests on: a title is never absent once a message has landed, so no
operator surface ever has to fall back to showing `conv-a3f81b2c` as a label.
"""

import pytest

from hub.conversations import title_from_message
from hub.db.models import CONVERSATION_TITLE_MAX_LENGTH

# ---------------------------------------------------------------------------
# The pure helper — no database, no model
# ---------------------------------------------------------------------------


def test_short_message_is_its_own_title() -> None:
    assert title_from_message("Fix the login redirect") == "Fix the login redirect"


def test_whitespace_and_newlines_collapse() -> None:
    assert title_from_message("  Fix  the\n\nlogin\tredirect  ") == "Fix the login redirect"


def test_empty_message_yields_no_title() -> None:
    assert title_from_message("") == ""
    assert title_from_message("   \n\t  ") == ""


def test_long_message_is_cut_at_a_word_boundary() -> None:
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliett kilo lima mike"
    text = " ".join([words] * 4)
    title = title_from_message(text)

    assert len(title) <= CONVERSATION_TITLE_MAX_LENGTH
    assert not title.endswith(" ")
    # No partial word: the title is a prefix of the source, ending where a space did.
    assert text.startswith(title)
    assert text[len(title)] == " "


def test_a_single_word_longer_than_the_limit_is_cut_rather_than_dropped() -> None:
    """Backing off to a word boundary would return nothing at all. Something readable wins."""
    title = title_from_message("x" * (CONVERSATION_TITLE_MAX_LENGTH + 50))
    assert len(title) == CONVERSATION_TITLE_MAX_LENGTH


def test_message_exactly_at_the_limit_is_untouched() -> None:
    text = "a" * CONVERSATION_TITLE_MAX_LENGTH
    assert title_from_message(text) == text


# ---------------------------------------------------------------------------
# Titling through the trigger path
# ---------------------------------------------------------------------------


async def _sync_agent(app, auth_headers, name="offline"):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert response.status_code == 200


async def _conversations(app, auth_headers, agent="offline", **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    suffix = f"?{query}" if query else ""
    response = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/conversations{suffix}", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_first_message_names_the_conversation(app, auth_headers) -> None:
    await _sync_agent(app, auth_headers)
    await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Investigate the flaky checkout test"},
        headers=auth_headers,
    )

    conversation = (await _conversations(app, auth_headers))[0]
    assert conversation["title"] == "Investigate the flaky checkout test"
    assert conversation["title_set_by_operator"] is False


@pytest.mark.asyncio
async def test_a_later_message_does_not_rename_the_conversation(app, auth_headers) -> None:
    await _sync_agent(app, auth_headers)
    first = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Investigate the flaky checkout test"},
        headers=auth_headers,
    )
    conversation_id = first.json()["conversation_id"]

    await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={
            "agent": "offline",
            "message": "Actually, start with the payment step",
            "conversation_id": conversation_id,
        },
        headers=auth_headers,
    )

    conversation = (await _conversations(app, auth_headers))[0]
    assert conversation["title"] == "Investigate the flaky checkout test"


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_rename_is_persisted_and_recorded_as_theirs(app, auth_headers) -> None:
    await _sync_agent(app, auth_headers)
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Investigate the flaky checkout test"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]

    renamed = await app.patch(
        f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}",
        json={"title": "Checkout flake"},
        headers=auth_headers,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Checkout flake"
    assert renamed.json()["title_set_by_operator"] is True

    assert (await _conversations(app, auth_headers))[0]["title"] == "Checkout flake"


@pytest.mark.asyncio
@pytest.mark.parametrize("title", ["", "   ", "\n\t "])
async def test_an_empty_rename_is_rejected(app, auth_headers, title) -> None:
    await _sync_agent(app, auth_headers)
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Investigate the flaky checkout test"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]

    rejected = await app.patch(
        f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}",
        json={"title": title},
        headers=auth_headers,
    )
    assert rejected.status_code == 400
    assert "empty" in rejected.json()["detail"].lower()
    # The original title stands.
    assert (await _conversations(app, auth_headers))[0]["title"] == (
        "Investigate the flaky checkout test"
    )


@pytest.mark.asyncio
async def test_an_over_length_rename_is_rejected_with_the_limit(app, auth_headers) -> None:
    await _sync_agent(app, auth_headers)
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Investigate the flaky checkout test"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]

    rejected = await app.patch(
        f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}",
        json={"title": "z" * (CONVERSATION_TITLE_MAX_LENGTH + 1)},
        headers=auth_headers,
    )
    assert rejected.status_code == 400
    assert str(CONVERSATION_TITLE_MAX_LENGTH) in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_a_conversation_predating_titles_is_named_on_first_read(app, auth_headers) -> None:
    """The live database had 35 of these. Without a backfill every one reads "New conversation".

    Lazy rather than a data migration: the migration would have to reproduce the truncation rule
    in SQL, and a conversation whose queue entries were pruned has no title to derive either way.
    """
    from sqlalchemy import update

    from hub.db.engine import async_session_factory
    from hub.db.models import Conversation

    await _sync_agent(app, auth_headers)
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Investigate the flaky checkout test"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]

    # Back to how a row created before this change looks.
    async with async_session_factory() as session:
        await session.execute(
            update(Conversation).where(Conversation.id == conversation_id).values(title=None)
        )
        await session.commit()

    listed = (await _conversations(app, auth_headers))[0]
    assert listed["title"] == "Investigate the flaky checkout test"

    # Persisted, not computed per request.
    async with async_session_factory() as session:
        stored = await session.get(Conversation, conversation_id)
        assert stored.title == "Investigate the flaky checkout test"
        assert stored.title_set_by_operator is False


@pytest.mark.asyncio
async def test_a_conversation_with_nothing_to_name_it_stays_untitled(app, auth_headers) -> None:
    """No message, no title — and the surface says "New conversation" rather than an id."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Conversation

    await _sync_agent(app, auth_headers)
    async with async_session_factory() as session:
        session.add(
            Conversation(
                id="conv-empty",
                project_id="proj-test",
                agent="offline",
                lifecycle="open",
                origin="operator",
            )
        )
        await session.commit()

    listed = (await _conversations(app, auth_headers))[0]
    assert listed["id"] == "conv-empty"
    assert listed["title"] is None


@pytest.mark.asyncio
async def test_rename_of_an_unknown_conversation_is_not_found(app, auth_headers) -> None:
    await _sync_agent(app, auth_headers)
    response = await app.patch(
        "/api/v1/projects/proj-test/agent/offline/conversations/conv-nope",
        json={"title": "Anything"},
        headers=auth_headers,
    )
    assert response.status_code == 404
