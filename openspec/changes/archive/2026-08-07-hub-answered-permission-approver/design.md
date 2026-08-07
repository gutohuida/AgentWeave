# Design

## The measured contract

`--permission-prompt-tool` is undocumented and hidden from `--help`, so the contract below was
derived by experiment against **Claude Code 2.1.221**, not from documentation. It is recorded here
because re-deriving it costs a spike and the details are not guessable.

**The flag is real.** `--permission-prompt-tool-bogus` fails with `error: unknown option`; the real
flag is accepted silently.

**Claude calls the named tool for each permission decision**, passing three arguments:

```json
{"tool_name": "Write",
 "input": {"file_path": "...", "content": "..."},
 "tool_use_id": "toolu_01A1ovzx54GPQRPZpTX2reDD"}
```

**`tool_use_id` must be accepted.** A tool declaring only `(tool_name, input)` fails every call with
`1 validation error for call[approve] / tool_use_id / Unexpected keyword argument`. The model sees
this as a broken approval system and reports being blocked, which reads like a Hub bug.

**The answer is a JSON string in a text content block:**

- `{"behavior": "allow", "updatedInput": <the original input>}`
- `{"behavior": "deny", "message": "<reason>"}`

**`structuredContent` must not be present.** This is the non-obvious part. FastMCP derives an output
schema from the return annotation and emits `structuredContent: {"result": "<the JSON string>"}`
alongside the text block. With it present, a correct `allow` is not honoured and the write is
refused — indistinguishable from a deny, with no error anywhere. Omitting the return annotation
suppresses structured output and the same `allow` then works.

Both paths were verified end to end under `--permission-mode manual`: `allow` let a write through;
`deny` blocked it and the model received and understood the message.

The verifying spike lives at `testbed/ppt-spike/` (git-ignored) and is disposable.

## Decision 1 — the decision is made in-process, and reported afterwards

The approval tool decides locally, in the MCP server process, against the run's own workspace. It
does not call the Hub to find out what to answer.

The governing constraint is the one `codex_appserver.decide_approval` already documents: *an
unanswered request hangs the turn forever*. A decision that requires a network round-trip to a Hub
that may be slow, restarting, or unreachable is a decision that can hang. Deciding in-process makes
the handler pure and total — every input maps to an answer, and the answer cannot fail to arrive.

The Hub is told afterwards, best-effort, so denials are visible to the operator. That report is
strictly observational: it is issued after the decision is determined, its failure is swallowed, and
it can neither change the answer nor delay it. If the Hub is down, the agent still gets an answer at
the same speed.

The alternative — routing each decision through a Hub endpoint — centralises policy and would make
operator escalation a change to the endpoint alone. It was rejected for now because it puts the Hub
on the hot path of every tool call and needs a timeout with a deny-on-timeout fallback, which
reintroduces the failure mode the in-process design removes outright. When
`2026-08-06-operator-in-the-loop-turns` is picked up, the reporting call is the natural place for
escalation to grow, and it can become blocking then, deliberately, for the postures that want it.

### How the workspace boundary reaches the MCP process

The MCP server is spawned as a standalone script and already reads `AW_RUN_TOKEN`, `HUB_URL`, and
`AW_AGENT_IDENTITY` from its environment. The run's effective working directory is threaded in the
same way, as a new environment variable. This is the same value `2026-08-06-...-base-knowledge`
already threads into the generated context as "Your workspace", so the boundary the agent is *told*
about and the boundary that is *enforced* come from one source and cannot disagree.

If that variable is absent, the tool denies rather than allows. A missing boundary is not an open
boundary.

### What counts as inside

A path argument is inside when its resolved absolute form is the workspace directory or beneath it,
after symlink resolution — comparing unresolved paths lets `..` and symlinks walk out. Tool calls
carrying no path argument are not path decisions and are allowed; the workspace boundary is a
filesystem boundary and is not the mechanism for restricting non-filesystem tools.

The Hub's own MCP tools are always allowed. They are how an agent collaborates, and they are already
constrained by the run's own credential.

## Decision 2 — the approver is not part of the agent's tool surface

The approval tool is registered on the same MCP server as the collaboration tools, because that
server is already spawned, credentialed, and reachable. But it is an endpoint the *harness* calls,
not a capability the *agent* has.

Two things follow. It is excluded from `_tool_surface_lines()`, so the generated "Your tools" section
does not advertise it — that section exists to tell an agent what it can deliberately use, and an
approval endpoint is not that. And its description is written for the harness, not as an invitation.

An agent can still technically call it, since `--allowedTools "mcp__agentweave__*"` matches by
prefix. That is acceptable: calling it returns a JSON decision string and changes nothing. It grants
no permission — Claude honours the answer to *its own* request, not to a call the model makes itself.
Narrowing the allowlist to an explicit tool list was considered and rejected as a larger change to a
line that is load-bearing for collaboration, for no security gain.

## Decision 3 — a fourth posture, and the default does not move

`permission_mode`'s `ControlDescriptor` gains a fourth value. Selecting it emits `--permission-mode
manual` *and* `--permission-prompt-tool mcp__agentweave__<tool>`; the other three postures are
unchanged and emit no approver flag.

It is labelled by what it permits — "Workspace only" — consistent with the existing labels being
written out rather than derived, which is why "Edit files" exists instead of "Acceptedits".

`acceptEdits` stays the default. "Workspace only" is strictly better in principle: it enforces the
boundary per tool call rather than trusting it. But it is new code on the path of every tool call,
and making it the default would make every existing agent's next run depend on it. The operator's
decision was to add it without moving the default, and to revisit after real use.

The approver flag is only emitted for this posture. Pairing it with `acceptEdits` would be nearly
inert, since edits are auto-accepted and never reach the approver; pairing it with `bypassPermissions`
would be contradictory. Emitting it only where it is meaningful keeps the argv honest.

### The ordering guard already exists

`_build_claude_command` suppresses its default posture whenever `control_args` supplied one
(`operator_set_permission_mode`). The new posture arrives through that same path, so it inherits the
guard. The approver flag must be appended under the same condition — a `--permission-prompt-tool`
that survives while its `--permission-mode` is overridden would point a posture at an approver it
never agreed to.

## Risks

- **The contract is undocumented and could change.** A future Claude Code could rename the arguments
  or start requiring `structuredContent`. Mitigation: the failure is loud — the model reports a
  broken approval system rather than silently gaining access — and a test asserts the exact response
  shape, including the absence of structured output, so drift fails locally rather than in front of
  an agent.
- **`structuredContent` can be reintroduced by accident.** Adding a return type annotation to the
  tool is enough to break it, silently and in the permissive-looking direction (a denied write looks
  like a refusal, not a bug). This is why it is asserted directly rather than inferred.
- **Path comparison is where boundary bugs live.** Symlinks, `..`, case-insensitive Windows paths,
  and relative paths all have to resolve before comparison. Tested explicitly, including the
  escape attempts, not just the happy path.
- **Best-effort reporting could become load-bearing by accident.** If a later change starts reading
  those records as an audit trail, the fact that they can be silently dropped matters. Recorded here
  so that change knows what it is inheriting.
