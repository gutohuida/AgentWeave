# Test guide — a Copilot agent uses hooks and its own agents

Each group can be cut. Skip the rows of any group the operator rejected.

## Agent-verifiable

### Group A: Copilot's lifecycle reaches the Hub

1. Task 1.1 records whether each subscribed raw-event type was delivered, and which of
   `session.error` and the `Error:` text chunk arrived first. The fixtures under
   `hub/tests/fixtures/copilot/` are in that recorded order.
2. Tests 1.2 to 1.6 fail before tasks 2.1 to 2.6 and pass after them. Test 1.3 uses the order task
   1.1 recorded (R3: the code sends the raw event first); its prose-before-error case keeps the
   prose as text, and its reversed-order case shows the order matters. Test 1.4's in-flight case
   passes, 1.2's token counts are integers, 1.2's oversized and subagent compactions behave as
   design D4 says, and 1.5's `payload: null` post answers 201.
3. `grep -rn "summaryContent" hub/hub` finds only the mapper line that drops it.
4. Drive 7.1: the timeline shows a paired `subagent_started` / `subagent_completed`.
5. Drive 7.2 (replaying the captured fixture; R2 found no bare `/compact` can reach Copilot): the
   script maps the fixture and `POST`s the event to `:8010`'s `/agents/cp5/output`, so the trial
   Hub's own process considers it (review 2026-09-28). The `compacted` card and the checkpoint-due
   banner both appear, and no checkpoint row is created under `offered`.
6. Drive 7.3: exactly one error event, still shown with diagnostics hidden, and no repeated `Error:`
   text.
7. Drive 7.4: no deciding hook and no trusted folder in the agent's Copilot home.

### Group C: BYOK

1. Tests 1.7 to 1.10 fail before tasks 3.1 to 3.3 and 3.5 and pass after them. Test 1.8's launchability
   assertions go through `GET /runners/launchability`, `GET /agents/launchability` and
   `POST /agents`, not the adapter alone; its stored-override case and 1.7's `PATCH` pair cases
   pass (R3). Review fixes 2026-09-28: 1.8 covers the checkpoint, handover and title spawns, the
   whole-prefix strip and the unset key; 1.9 carries the key through text, thinking and a
   permission card, and in a format no pattern matches; 1.7 covers the localhost look-alikes, the
   `api_key` paste (400, no echo) and `--model` in flags.
1a. (No group, never cut.) The no-provider halves of tests 1.6 and 1.8 pass: no `COPILOT_ALLOW_ALL`
   and no `COPILOT_PROVIDER_*` from the Hub's environment or `env_vars` reaches any Copilot spawn
   without a provider, whichever groups were kept (task 2.8).
2. Drive 7.5: the pasted-key refusal sentence is recorded verbatim, and a read-only grep of the
   trial database finds no key value.
3. The Runners page shows the API-key and Claude Max sentence (test 1.14).

### Group B: review agents

1. Tests 1.11 and 1.12 fail before tasks 4.1 and 4.2 and pass after them. The verdict line is
   byte-identical with the setting on and off.
2. Drive 7.7: the context bullet names `<base>..<commit>`, a `code-review` subagent ran, and the
   verdict was recorded by `update_task`.

### Group D: GitHub server toggle

1. Test 1.13 fails before task 5.1 and passes after it, including every non-`agentweave` server
   asking under its own name while the toggle is on, and an unreported server refused (DECIDED
   2026-09-28).
2. Drive 7.8: the live process's command line carries the flag when the toggle is off, and a card
   saying the call acts on GitHub as the operator, with no "Workspace only would …" line, appears
   for a GitHub-server call when it is on.

### All groups

- `openspec validate a-copilot-agent-uses-hooks-and-its-own-agents --strict` passes.
- The CI command set in task 6.1 is green.

## Human-only

1. **Hooks (D2).** Do you still want a Hub hook for anything, now that raw events carry compaction,
   errors and subagents with more detail? If yes, name the event and what it should feed.
2. **Compaction behaviour.** On a real Copilot conversation long enough to auto-compact (about 80%
   full), under `automatic`, does the handover feel right mid-turn? Under `offered`, the banner
   keeps its threshold sentence and the timeline shows a "Copilot compacted this conversation" card
   (R2: nothing can show a banner variant without a persisted fact). Is that enough, or do you want
   the banner itself to say the runner compacted?
3. **BYOK happy path.** Put an Anthropic API key in the trial Hub's environment, bind a Copilot
   provider runner on Haiku, and run a turn (task 7.6). Does it complete? Is the spend shown in
   tokens, with no misleading "0 credits"? Know that the key is in the run's own environment, so
   the agent's shell commands and the Hub's tool server can read it, as with a proxy runner today;
   what they print back is redacted by its exact value. Is that acceptable? OpenAI BYOK is deferred
   (R2). Recommended by the 2026-09-28 review (your call): only after the scrub, the prefix strip and
   the URL check are built, with a dedicated Anthropic workspace key with a hard monthly spend limit
   of a few dollars, set only in the trial Hub's launch environment, and revoked afterwards.
4. **Runner page copy.** Read the provider section. Is it clear that a Claude Max subscription cannot
   be used and that the key stays in the Hub's environment?
5. **Review agents.** On a real review, does consulting `code-review` improve the verdict enough to
   justify the extra model calls? Would you turn it on by default for Copilot reviewers?
6. **GitHub server (work PC).** On the Business plan, enable the toggle for one agent. Do the cards
   for GitHub calls read as "this acts as you on GitHub"? Does company policy allow the built-in
   server at all?
7. **Work PC, hooks policy.** Check whether `allowManagedHooksOnly` is set there (exploration probe
   6). If it is, that confirms D1's reason to rely on raw events rather than hooks.
