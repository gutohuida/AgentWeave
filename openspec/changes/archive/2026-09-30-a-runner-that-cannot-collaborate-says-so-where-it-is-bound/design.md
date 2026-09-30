# Design — a runner that cannot collaborate says so where it is bound

## Operator review, 2026-09-24

The Opus adversarial review found that the fix does not reach the operator in the one flow it
exists for. The operator decided to fix it (D6 below) and approve the rest unchanged.

- **The warning stayed up after the operator fixed the runner.** `useUpdateRunner` and
  `useDeleteRunner` invalidate only `['project', pid, 'runners']` (`hub/ui/src/api/runners.ts:92`,
  `:106`). The verdict this change renders is read under `['project', pid, 'agents',
  'launchability']` with `staleTime: 30_000` (`hub/ui/src/api/agents.ts:379-387`), a different
  prefix. So removing `--no-app-server` or enabling yolo on the runner left the line on screen, and
  the test guide's step 2 said to "record which" instead of requiring the line to go. New design D6,
  tasks 1.5 and 2.1a, and test-guide step 2 now require it to disappear without a reload. The
  ADDED requirement gains one sentence and the scenario *"Fixing the runner clears the warning
  without a reload"* so that this is part of the contract, not only of the tasks.

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

## D6 — editing or deleting a runner re-reads the agents' verdict (operator review)

The fix the line asks for is made on the runner, not on the binding: *"remove the flag or enable
yolo"* is an edit on the Runners page, through `useUpdateRunner` (`hub/ui/src/api/runners.ts:86-94`).
That hook, and `useDeleteRunner` (`:96-108`), invalidate `['project', pid, 'runners']` only. The
per-agent verdict is `useAgentLaunchability`'s `['project', pid, 'agents', 'launchability']`
(`hub/ui/src/api/agents.ts:379-387`), under the `agents` prefix, with a 30 s `staleTime`. Rebinding
refreshes it (R3, via `useBindAgentRunner`'s `['project', pid, 'agents']`). Editing the runner
does not. The operator would fix the runner, return to the agent, and still read *"cannot
collaborate"*.

So both hooks' `onSuccess` also invalidate `['project', pid, 'agents', 'launchability']`. The
runner-side keys (`['project', pid, 'runners', 'launchability']` and `…, 'launchability-by-
provider']`, `runners.ts:56`, `:69`) are already under the `runners` prefix and need nothing.
`useCreateRunner` is left alone: a new runner is bound to no agent, so no agent's verdict can change.
Deleting a bound runner does change one: the agent becomes `runnable: false`, and the cannot-run
line must appear. `onSuccess`, not `onSettled`, matching the hooks' existing shape: a failed edit
changes nothing a verdict depends on.

## D7 — the reason names each remedy by the name the app shows (R2, 2026-09-30)

R2 re-derived D1–D6 on master `bdc8447`. They stand. `a-copilot-agent-runs-over-acp` (archived today)
edited `runners.ts` and the launchability docstring. It left `useUpdateRunner` and `useDeleteRunner`
invalidating only `['project', pid, 'runners']`, and the collaboration branch unchanged. A Copilot or
Claude runner falls into its `else` and is always `collaboration_ready: true`.

One gap: the sentence this change puts on screen ends *"Remove the opt-out, or enable yolo."*
(`agents.py:268`). The app never shows the word "yolo". The setting is the agent's default
permission posture, which `model_catalog.py` labels **Full access** (`bypassPermissions`), and
`set_default_permission_mode` keeps `config["yolo"]` equal to it (`agents.py`, "keep `config["yolo"]`
saying the same thing"). The opt-out is a flag on the *runner* (`--no-app-server`). The requirement
this change adds says the reason names the condition *"where it can be fixed"*. A remedy phrased as
a setting the operator cannot find does not do that.

A second gap, found while writing task 1.5: **the app cannot edit a runner's flags, or show them.**
`PATCH /runners/{id}` accepts `flags` (`schemas/runners.py` `RunnerUpdate`), but the UI's `RunnerUpdate`
(`api/runners.ts`) carries only `name` and `model`, and no component renders or sets `flags`. A
flagged runner exists only because something called the API. So "remove the opt-out", which D6 and
test-guide step 2 assumed the operator does on the Runners page, is not something the app offers.
Filed as F469. It is not fixed here: flags are free-form CLI arguments, and editing them is its own
change.

So the Hub's sentence names two remedies the app does offer, as it labels them: bind a runner without
`--no-app-server` (the picker directly above the line; `useBindAgentRunner` already refreshes the
verdict), or set this agent's permissions to Full access. It still leads with "silently
denied", which `test_launchability.py` asserts on. Choosing Full access already refreshes the
verdict: `useUpdateAgentPermissionDefault` invalidates every `['project', pid, 'agents', …]` key,
the launchability key included. D6 is narrowed by the drive (2026-09-30, below).

What the route returns when what it calls raises is unchanged: the sentence is a literal.

**Drive, 2026-09-30** (throwaway Hub `:8032`, profile `drive0930b`, project `proj-7b2768097be5`, no
model call; script in the session scratchpad, `d0930_collab.py`). A Codex runner created through the
API with `["--no-app-server"]`, an agent bound to it, `GET /agents/launchability` after each step:
flagged + default posture → `runnable: true, collaboration_ready: false`, with the new sentence (names
`--no-app-server` and Full access, no "yolo"); Full access → `true`; posture cleared → `false`;
rebound to a flagless Codex runner → `true`. **Deleting the bound runner answered 409** ("Runner is
bound to agent(s): … Unbind before deleting."), and the verdict stayed `true`. So D6's premise that
deleting a bound runner changes an agent's verdict is wrong: the Hub refuses that delete, and an
unbound runner's delete changes no verdict. `useDeleteRunner` is therefore left as it was, and only
`useUpdateRunner` re-reads the verdict (a model edit changes the probe, which reads the bound
runner's `cli`/`model`). Task 1.5's delete case became a control, and test-guide step 2 drops it.

