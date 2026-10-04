# A secret split across two events is still scrubbed

## Why

**F488 (B).** Slice 5 group C (`a-copilot-agent-uses-hooks-and-its-own-agents`, design D7, task
3.5) registers a run's provider key with `run_secrets` and removes it by its exact value from
everything the run records. The removal works on **one event at a time**:
`record_agent_output` (`hub/hub/output_recording.py:44-45`) calls `run_secrets.scrub` on that
event's `content` and `payload`, and `scrub` replaces whole literal occurrences
(`hub/hub/run_secrets.py:50-56`).

Model text is not recorded as one event. It is recorded as a sequence of `thinking` and `text`
events, with tool events between them. `CopilotEventMapper.on_session_update`
(`hub/hub/copilot_acp.py:1019-1048`, at `13f7421`) joins streamed chunks into blocks, and emits a
block as an event whenever the stream switches between thought, message and tool call, and (since
`d08c2f5`, `_after_open_blocks` at `:1233-1238`) whenever a raw event produces an error, compaction
or subagent card. So when a key's characters fall on both sides of a switch, each event holds only part of it. Each part passes
the scrub. The timeline shows the two rows one after the other, and the reader sees the whole key.
`cp5` reproduced this with `plainproxykey123`, split as `plainproxy` + `key123` (F488, during drive
task 7.7).

The mapper is not the root cause. Claude and Codex record whole content blocks (`thinking`, `text`,
reasoning, agent message) as separate events too (`hub/hub/runner_parsing.py:282-287`,
`hub/hub/codex_appserver.py:415-429`). A value that spans two of a model's own blocks splits the
same way on every runner. A Copilot provider runner always registers its key
(`hub/hub/api/v1/agent_trigger.py:1616`); a Claude or Codex run registers one only when the Hub's
own environment or the agent's `env_vars` carry `COPILOT_PROVIDER_API_KEY` (design, *Which runs
register a value*). The drive saw it on Copilot.

The guarantee D7 states, that "neither the row nor the broadcast ever holds them", holds for each
row and fails for the run.

## What Changes

- **The scrub carries across a run's text.** For each run with registered values, the Hub
  remembers the last characters of the model text it has recorded (`text` and `thinking`
  events, in recording order), one character fewer than the longest registered value. Each new
  text or thinking event is checked together with that tail. Where a registered value runs across
  the boundary, the part inside the new event is replaced with `<redacted>`. Whitespace at an event
  boundary is skipped when joining, because the reader cannot see it and Copilot does not strip
  its thinking text (design D1, R3).
- **A text event that ends with the start of a value loses that start.** When a text or thinking
  event ends with the first *m* or more characters of a registered value, where *m* is half the
  value's length but never more than 8, those characters are replaced with `<redacted>` when the
  event is recorded, without waiting to see what follows. A shorter dangling start, at most 7
  characters, is recorded as written, and if the next event completes the value, the rest is
  redacted there. For an `sk-ant-…` key, those 7 characters are the public `sk-ant-` prefix.
- **Nothing is held back.** Every event is recorded and broadcast when it arrives, in the order
  it arrives. Tool cards and the text around them are not delayed.
- **The tail spans every other kind.** A value split as text, tool card, text (or around an
  error, compaction or subagent card) is redacted the same way as text followed directly by text.
- It is applied **once per event, where the executors record the run's stream**: the Claude and
  Codex `exec` loop and the RPC executor's `_on_event` (`agent_trigger.py:2836-2856`,
  `:3763-3784`), in the same synchronous step that assigns the event's `sequence`, so the tail
  follows the order the timeline reads even when two `_on_event` calls interleave. It is not
  applied inside `record_agent_output`, because `_record_observation`
  retries that call on a locked database (`agent_trigger.py:2257-2275`), and a retry would feed
  the same text in twice. `record_agent_output`'s per-event scrub stays as it is, as the floor for
  every kind and every caller.
- `run_secrets.forget` also drops the run's tail.
- **`run_secrets.register` strips each value** (design D7, from the pre-approval review): a key
  resolved with a trailing newline or space is registered without it as well as as written, so
  the model's copy of it, which carries no such whitespace, is matched.
- **The `session.error` log line is scrubbed** (design D6; R2- and R3-recommended, subject to the
  operator's open question 3). `copilot_acp.py:2124-2130` logs a `session.error` payload whole to
  the Hub log; it is passed through `run_secrets.scrub` with the run's id before it is serialised
  and cut at 2000 characters. If that scrub raised, the line is logged without its payload and the
  raw event still reaches the mapper.

## Non-Goals

- **Joining any kind other than `text` and `thinking`.** Tool inputs and outputs, diagnostics,
  errors, status rows, lifecycle events, permission cards and `Run.error` each hold one complete
  string from one source. They are scrubbed per event, as now.
- **Self-reported output** (`POST /agents/{name}/output`, `hub/hub/api/v1/agents.py:3178`) is not
  joined to the run's stream. It is scrubbed per post, as now.
- **A value cut by truncation.** `text_event`, `thinking_event` and the tool builders truncate
  before the scrub runs (`hub/hub/runner_events.py:171-184`, `:213`, `:242`). A value straddling a
  64 KiB or 8 KiB cut leaves a prefix in that row, and the rest is never recorded. That is a
  prefix, not the whole value. The new rule catches it only when the cut row ends with *m* or more
  characters of the value.
- **Fragments that are not at an event boundary.** Exact-value matching has never hidden a part of
  a value that the model writes on its own, and this change does not start. That includes a value
  split across two parts of one Codex app-server reasoning item, which the Hub joins with a space
  inside one event (`hub/hub/codex_appserver.py:426-428`): it is inside an event, so it is not joined.
- **A registered value that contains whitespace, split at that whitespace.** Whitespace at an event
  boundary is skipped when joining, so such a value is not matched across that boundary (design
  D1). API keys contain no whitespace.
- **A value split across two runs.** The tail is per run and in memory; the next run of a
  conversation, or a Hub restart, starts with none (design D1).
- **What an agent writes through the Hub's MCP tools** (`send_message`, `ask_user`, task updates,
  checkpoint notes, evidence, spec documents). None of those routes scrubs registered values at all
  today; that is a separate gap, filed as its own finding, not a split-value case.
- **Holding events back** so that no fragment is ever visible. Rejected in design D3; see the
  operator's open question 1.
- **The Hub's log beyond the `session.error` line.** No other log line is known to carry model
  text or a provider error payload; none is swept here. The nearest are the 200-character quotes
  of a non-JSON stdout line (`copilot_acp.py:1639`, `codex_appserver.py:800`), which carry
  whatever the CLI printed outside its protocol; not observed to carry a key.
- **No migration, no UI change, no backfill.** Rows already stored stay as they are.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-stream-events`: an ADDED requirement saying that a run's registered values are removed
  from its recorded text when two or more events split them. The exact-value requirement itself is
  in slice 5's unarchived `runner-registry` delta (*A Copilot runner may reach its model with the
  operator's own API key*), so this change adds to the stream contract and does not modify that
  requirement.

## Impact

- `hub/hub/run_secrets.py`: per-run tail state, a `scrub_stream(run_id, event)` that returns the
  event with `content` and `payload["text"]` rewritten for `text` and `thinking` events,
  `forget` clearing the tail, and `register` keeping each value stripped as well as raw.
- `hub/hub/api/v1/agent_trigger.py`: the two stream-recording sites call it, beside
  `sequence += 1`, before building the `_record_observation` write.
- `hub/hub/copilot_acp.py`: the `session.error` log line scrubs its payload, and logs it without
  the payload if the scrub raises (D6, if open question 3 is answered "fold in").
- Tests: `hub/tests/test_run_secrets_stream.py` (new), `hub/tests/test_copilot_byok_env.py`
  (driven through the real `CopilotEventMapper`, including the card boundaries), a Claude-stream
  case, and a `caplog` case for the log line.
- No change to `runner_events.redact_secrets` (F278's `_redaction_for`). The two apply to disjoint
  kinds (design D5).
