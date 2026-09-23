# Design — a runner that cannot collaborate says so where it is bound

**Built on the recommended answer to D6 for F178: build, by extending the mount F179 already made,
and delete the dead card.** If the operator answers *delete*, this change is replaced by a smaller
one. It would delete `AgentCard` and its test, remove `collaboration_ready`/`collaboration_reason`
from `GET /agents/launchability`, and REMOVE `runtime-diagnostics`' *"Collaboration readiness is
checkable before it is needed"* (`openspec/specs/runtime-diagnostics/spec.md:137-163`). R1
recommends against that (D1).

## D1 — build, not delete

| | Build (recommended) | Delete |
|---|---|---|
| Operator | Sees why a Codex agent's tool calls will be denied, where they bind its runner | Finds out when a peer never hears back |
| Code | One conditional line in a component that already has the data; two files deleted | Two UI files and two payload fields deleted; the route's collaboration branch deleted |
| Spec | One ADDED requirement | One requirement REMOVED |

The fact exists because the failure it predicts is silent. Denials happen *"with no operator present
to approve them"*. Deleting the report leaves a silent failure with no warning, which is a barrier
the operator cannot see. Codex being undrivable on this machine (plan cancelled 2026-08-29) does
not change the product: Codex runners are still created and bound, and the app-server opt-out is
still a flag (`hub/hub/codex_appserver.py:73`). Building costs a few lines. That makes it the
cleaner answer.

## D2 — where, and why not the rail

- **The runner picker.** An operator binds a runner there, and it is the only place a fix happens:
  the reason tells them to remove the flag or enable yolo. It already shows the `runnable: false`
  sentence (F179), so both launchability facts appear in one place, in the same form.
- **Not the rail.** The rail (`AgentTree.tsx`) is an index of conversations. Putting a probe
  verdict there would make every project load call `/agents/launchability`, which F178 measured
  was not among the 41 requests a load makes. The operator would also get an amber badge (the old
  card's *"CANNOT COLLABORATE"*) in a place they cannot act on it. R2 may weigh this differently.
  R1 found no operator statement about the rail either way.
- **Not the composer.** The composer's target picker, where the badge first lived, no longer exists
  (`AgentCard.tsx:12-14`).

## D3 — the precise condition

```ts
const cannotCollaborate = verdict?.runnable === true && verdict.collaboration_ready === false
```

`runnable === true` is required because the Hub computes collaboration only when the agent is runnable
(`agents.py:241`). A `runnable: false` verdict always has `collaboration_ready: null`, and the
cannot-run line already speaks for it. So the two lines never appear together. If the reason is
missing, the line falls back to *"the Hub reports its tool calls would be refused"*, the same
fallback shape the cannot-run line uses.

**What the route returns when what it calls raises.** Unchanged. `get_agents_launchability` does
not catch anything: a `probe_agent` or database error is a 500. `RunnerPicker` already renders
*"Could not check whether this agent can run."* when `launchabilityError` is set and no verdict is
cached (`AgentSettingsControls.tsx:258-263`), so a failed read is not shown as *"ready"*.

## D4 — deleting `AgentCard`

Its only importer is its own test. Its props (`agent`, `selected`, `onClick`, `launchability`) are
duplicated on screen by the rail row (`hub/ui/src/components/layout/AgentTree.tsx`) and the
conversation header, except for the collaboration badge, which moves under D2. Keeping an unmounted
component that a test certifies is how F178 went unnoticed for 24 days. The test's own opening
comment says the indicator *"moved here — the place an operator looks"* while nothing mounted it.
`useAgentLaunchability` stays consumed, by `RunnerPicker`.

## D5 — collisions with other open changes (R2)

- `agents-no-longer-register-themselves` task 2.9 removes the `EXT` badge from `AgentCard.tsx:65-72`.
  If this change lands first, that step has nothing left to edit and is dropped. If it lands
  second, this change deletes the file as planned. Neither needs the other.
- `a-runner-choice-names-its-model` task 2.2 edits `RunnerPicker`'s `<option>` labels, the same
  component. The two edits touch different lines (the options, and the status lines below the
  `Select`). This is a textual merge only.
- The picker can now show two `role="status"` lines, the cannot-run line and this one, though never
  both for one verdict (D3). Tests find each line by its text, not with a single
  `getByRole('status')`.
