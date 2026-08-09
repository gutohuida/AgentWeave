# Checkpoint configuration surface

## Why

`2026-08-07-conversation-handoff-rework` shipped checkpointing with its configuration reachable
only over the API. Everything works — thresholds resolve, the trigger fires, cutover happens — but
an operator cannot turn any of it on without writing JSON. The shipped spec says *"Token thresholds
are entered in thousands"*, which describes an entry surface that does not exist, and `design.md`
asks for both readings to be shown (`"150k — 75% of Haiku 4.5's 200k"`), which nothing surfaces.

**A destructive bug came with it, and is the more urgent half.** `PUT /projects/{id}/settings`
replaces every field from its Pydantic model, filling omissions with defaults. The settings panel
sends six fields, because `ProjectSettingsInput` is a `Pick` of `ProjectSummary` and
`ProjectSummary` carries neither the checkpoint fields nor the conversation-title fields. So
pressing **Save settings** silently resets `checkpoint_mode` to `off` and clears the threshold, the
notes point, the runner and the model.

Reproduced live against a configured project: eight fields in, eight fields gone, HTTP 200.

The same shape has been latent for `conversation_title_mode` since it was added — it survives only
because its default happens to equal the common value. Adding six more fields turned a dormant trap
into an active one. A comment at that field records the reasoning: *"Defaulted rather than required
so a client written before this field still round-trips."* That is precisely what makes the reset
silent rather than a 422.

## What changes

- The settings panel reads and writes the **whole settings representation**, so a field added to
  `ProjectSettings` can never again be reset by a client that has not heard of it.
- Project-level checkpoint controls: mode, threshold in proportion **or** thousands of tokens with
  both readings shown, notes point, generating runner and model.
- Agent-level controls: the threshold override, presented as a whole threshold or none, and the two
  access grants.

## Impact

- `hub/ui/src/api/projects.ts`, `hub/ui/src/components/environment/ProjectSettingsPanel.tsx`
- `hub/ui/src/api/agents.ts`, `hub/ui/src/components/agents/AgentSettingsPage.tsx`
- `hub/hub/api/v1/projects.py` — a regression test, and the hazard recorded where it lives
- No migration. Every column already exists.
