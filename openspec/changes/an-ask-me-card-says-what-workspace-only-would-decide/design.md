# Design — an "Ask me" card says what "Workspace only" would decide

**Built on the recommended answer to D4's second half: yes, the card shows the verdict, as advice.**
If the operator answers no, F230 and F284 close as "by design" with a line in the posture
documentation, and this change is dropped whole. **Built also on D5's recommended answer** (bare
expansions other than the directory variables stay allowed), which is why step 5 of the proposal
exists: the card must not print "inside" over a command whose destination is a variable.

**R1, 2026-09-24.** file:line at `ce086b6`.

## D4 (second half) — the options

| Option | What the operator sees | Cost | Verdict |
|---|---|---|---|
| (a) No verdict (today) | tool + path/command | the operator must spot a boundary the Hub already computed | rejected (F230, F284) |
| **(b) The approver's own `_decide` verdict, advisory** | tool + path/command + "Workspace only would refuse/allow this: reason" | one optional field, one column, one line of UI | **recommended** |
| (c) "Ask me" refuses outside-workspace calls itself and asks only for the rest | fewer cards | changes what the posture means; the documented contract is that under a posture that checks nothing the operator is the boundary (`agent-run-sandboxing`, *"The product states which postures confine a run"*) | rejected: a new posture, not a card |
| (d) The Hub classifies server-side from `Run.workspace_dir` via `workspace_writes.classify` | "which workspace" for file tools | no shell reading: the judge lives in `mcp_server.py`, which is spawned standalone and reads its boundary from the environment (`_decide`, `:1537-1586`); a second classifier is a second opinion, which `outside_write_record.py`'s docstring rejects | rejected as the source; a later change could add classify's destination kind for file tools |

**Consistency with D4's first half and D5.** Under the recommended default (`workspace`) the verdict
on the card is the exact answer an unattended run of the same agent gets, from the same function; an
operator comparing the two sees one boundary.

## Decisions

### D1 — The verdict is computed where the answer would be

In `_ask_operator` (`hub/hub/mcp_server.py:1624-1649`), before opening:
`verdict = _decide(tool_name, tool_input)`. `_decide` is pure and total (`:1537-1586`) and reads only
`AW_WORKSPACE_DIR`, which the Hub sets for every run (`agent_trigger.py:1192`), under both postures.
For an `mcp__agentweave__*` tool the operator is never asked (`:1703`), so no verdict is needed.

For Codex, `_await_operator_permission` gains `workspace: Optional[str]` (the lambda at
`agent_trigger.py:3021` has `work_dir` in scope) and computes
`codex_appserver.workspace_verdict(subject, workspace)`, a new helper that returns
`{"allow": _within(cwd or grantRoot, workspace), "reason": …}` — the check `decide_approval` applies
under "Workspace only" (`codex_appserver.py:280-283`).

### D2 — The protocol change survives an un-restarted Hub

`PermissionRequestCreate` is a `RequestModel` with `extra="forbid"` (`schemas/common.py:21-32`). The
operator's `:8000` spawns `mcp_server.py` fresh from the checkout on every turn but runs its Hub code
until restarted. A new approver sending `workspace_verdict` to that Hub gets a **422**, `_ask_operator`
catches it (`:1643`) and denies: *every "Ask me" card on `:8000` would fail* until the restart.

So: `_ask_operator` posts with the field; on `HubAPIError` with status 422 (`_hub_request` raises it,
`:187-198`) it posts once more with today's body. A 422 is raised by validation before the handler
runs, so no row was created and the retry cannot open a duplicate card. Any other failure keeps
today's answer ("the operator could not be asked"). A test covers both (task 1.3).

**What `open_permission_request` returns if something raises:** a malformed verdict is a 422 (then
the retry above); a database failure is today's 500, answered by the approver as today. The route
does no computation of its own on the verdict: it stores it.

**Trust.** The field comes from the approver process under the run's credential. An agent could open
a request of its own with a false verdict, but nothing waits on a request the approver did not open
(`_await_decision` polls its own id, `:1652-1689`), and the verdict decides nothing. Identity is not
taken from the body (unchanged).

### D3 — Stored as data, shown as advice

`permission_requests.workspace_verdict`: nullable JSON (migration `0106`, guarded for a missing
table as `0033`/`0034` do; head assertions bumped). Schema: `allow: bool`, `reason: str` with
`max_length=MAX_REASON_CHARS` (1000, `agent_actions.py` `PermissionDecisionCreate`), which every
`_decide` reason already fits (`_QUOTATION_MAX`, `mcp_server.py:1082`; *"A refusal's reason fits the
record that carries it"*). The response model adds `workspace_verdict: dict | None`.

Card (`PermissionRequestCard.tsx`, after the `<code>` at `:112-117`):
- `allow === false` → `data-testid="permission-verdict-<id>"`, warning colour: "Outside this agent's
  workspace — Workspace only would refuse this:" + reason.
- `allow === true` → muted: "Workspace only would allow this." For a command, append "A shell
  command is read, not sandboxed."
- `null` → nothing.
`requestKind` is unchanged.

### D4 — An allow reason stops overclaiming

`_decide` returns `"inside your workspace"` (`:1586`). For a command in which any word or nested
substitution expands (`_expands` true on some word, or `nested` non-empty in `_lex`), it returns
*"inside your workspace as far as its text shows; it names a value the shell decides when it runs"*.
Only the reason changes; `allow` does not. `approve_tool_call` sends no message on an allow
(`:1711-1712`), so the model sees nothing new.

## Risks

- Migration reaches `:8000` on the operator's next restart (tell them, as the rules require).
- The UI bundle reaches `:8000` on reload; with an old Hub the field is absent and the card shows
  nothing extra (the `null` case).

## Open questions

1. D4's second half (recommended (b)).
2. Should the Questions page's decided-permissions list (UI-1, F231) show the verdict too? Recommended
   later, not here.
