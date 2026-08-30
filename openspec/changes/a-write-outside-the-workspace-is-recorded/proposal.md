## Why

An agent's worktree is its working directory, not a wall. On 2026-08-29, driving rows 13 and 14 of
the sweep, the same agent given the same instruction in different words wrote to
`.agentweave/worktrees/asker/drive-note.txt` on one run and to
`C:\…\drive-2026-08-29\drive-note-121250.txt` — the operator's own checkout — on another. Nothing in
the product decided that. The model spelled the path differently the second time. **F115.**

All four runs of that drive recorded the same `workspace_dir`:

```
run-cd72f733910f | C:\…\drive-2026-08-29\.agentweave\worktrees\asker
run-c10e35f30d81 | C:\…\drive-2026-08-29\.agentweave\worktrees\asker
run-e3f1a39c2a14 | C:\…\drive-2026-08-29\.agentweave\worktrees\asker
run-72de0f5c6898 | C:\…\drive-2026-08-29\.agentweave\worktrees\asker   <- wrote outside it
```

The Hub believes all four ran in the worktree. Three did. One wrote into the checkout the worktree
exists to protect, and **nothing recorded that it had**.

The operator decided the shape on 2026-08-29 and completed it on 2026-08-30 (`scripts/drive/FINDINGS.md`,
F115): the worktree is only ever a cwd, the operator is the boundary, native mode is **not** to
acquire containment, and containment stays something the product buys from an OS-level sandbox if it
ever wants it. What is missing is not a wall. It is a **record**.

### Round 1 correction: the finding's premise about the default posture is wrong

F115 says that "in the posture an operator is most likely to be running, nothing shows the path and
nothing constrains it." Reading the code says otherwise, and the difference matters for what this
change is allowed to claim.

`DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE` (`hub/hub/runner_commands.py:66`). The
default posture for a non-yolo Claude run is `workspace`, which routes every tool call through
`--permission-prompt-tool` to `mcp_server.approve_tool_call`, and `mcp_server._decide`
(`hub/hub/mcp_server.py:864-916`) already refuses a path outside `AW_WORKSPACE_DIR`, on
`os.path.realpath` + `os.path.commonpath`, so `..` and symlinks are collapsed before the comparison.
There is a shipped requirement of record for it — `agent-run-sandboxing`, *"A posture exists in which
the workspace boundary is enforced per tool call"*.

So the default posture **does** constrain the exact call F115 reproduced. And the run that escaped,
`run-72de0f5c6898`, was **`manual`** — the posture in which the *operator* answers, and the card it
raised named the tool and the full absolute path:

```
tool_name: "Write"
tool_input: {"file_path": "C:\…\drive-2026-08-29\drive-note-121250.txt", ...}
```

The escape was an approval, not a hole in the default.

This does not soften the finding and does not disturb the operator's decision. It relocates it. The
gap is not "the default posture is blind"; it is that **an outside-the-workspace write leaves no
trace in any posture where it is possible**, and there are four such postures:

| Posture | Outside-the-workspace write | Recorded anywhere today |
|---|---|---|
| `workspace` (default, Hub answers) | refused by `_decide` | the refusal is (`A refusal is recorded wherever it is decided`) |
| `manual` (operator answers) | **allowed if the operator approves** | no |
| full access / `--dangerously-skip-permissions` | **allowed, no check at all** | no |
| `acceptEdits` (fallback where no Hub MCP server is configured, `runner_commands.py:73`) | **allowed, no path check at all** | no |

Plus one that survives even under `workspace`: a shell command that builds its path at runtime.
`_decide` reads absolute paths out of the command *text* and says so of itself — *"This does not make
shell escape impossible … and is a boundary, not a sandbox."*

The product therefore already refuses what it can refuse. What it does not do is **notice**. That is
this change.

### Why it matters beyond the stray file

- **Evidence is footprinted at `Run.workspace_dir`** (F71; `hub/hub/requirement_evidence.py:337`,
  design D7 of `2026-08-27-work-is-isolated-per-task`). Work written outside that directory is
  invisible to footprinting: the footprint reads the worktree, finds nothing, and presents a partial
  tree as a complete one. `requirement-traceability` already says a footprint that silently describes
  a tree other than the one named is *worse than absent evidence*.
- **Per-task isolation** rests on the same assumption. Its guarantee — approving one task cannot ship
  another task's unreviewed work — holds only for agents that use relative paths.
- **The cross-worktree variant is worse, and it is why the record must name a destination.**
  `snapshot_worktree` (`hub/hub/worktrees.py:737-786`) runs `git add -A` in the worktree and commits
  whatever is there onto that agent's branch under `Auto-snapshot: <agent>'s turn`. A write by alice
  into bob's worktree is therefore **auto-committed to bob's branch, labelled as bob's turn**, and
  flows through review, evidence and merge looking legitimate. It does not merely escape isolation;
  it launders work through the wrong identity. Nothing in `git status` ever shows an operator that
  alice did it.

### Round 2, 2026-08-30: what an independent re-derivation changed

Round 2 read the code fresh against this proposal rather than re-reading round 1. The premise
correction above **survives** — `DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE`
(`runner_commands.py:66`, applied at `:220`), so the default posture really does check — and so does
the argument that `work_dir` and `AW_WORKSPACE_DIR` are one value. Six things did not survive; the
two that matter to a reader of this proposal are:

- **The change as written covered one of three transports.** The field was on `ParsedLine`, and the
  Codex app-server path never reaches `_flush_line` at all. The carrier moves to `RunEvent`, which
  all three transports produce — design D2.
- **It appeared to breach a shipped requirement in the capability it adds to.** `agent-run-sandboxing`
  says *"Only refusals SHALL be recorded"*, and this change's operator notification records a write
  that was **allowed** — so round 2 added a MODIFIED delta narrowing the sentence. Round 3 disproved
  the premise; see below.

The full list, with what was re-derived and left standing, is in `design.md` under
*Round 2 corrections, 2026-08-30*.

### Round 3, 2026-08-30: what a second independent re-derivation changed

Round 3 read the code against the proposal without re-reading round 2's reasoning. The change is
still not implemented. Six corrections; the three that matter to a reader of this proposal:

- **Round 2's breach was not a breach.** *"Only refusals SHALL be recorded"* constrains the refusal
  record, not every durable event the Hub keeps. The disproof is a measurement rather than a reading:
  `persist_event` carries **44 distinct event types** in the shipped Hub and exactly one of them —
  `permission_denied` — is a refusal. Round 2's reading convicts the product 43 times over, and the
  requirement's own fourth scenario already says the narrow thing (*"not recorded **as refusals**"*).
  The notification stays. The MODIFIED delta shrinks to the two-word clarification plus one sentence
  of scope; the policy paragraph round 2 wrote into a requirement about refusals is removed, and the
  fact it pinned moves into this change's own ADDED requirement, where it belongs. **Round 2 edited
  the corpus to fit the change without first checking whether the product already breached the
  sentence it was fitting to.**
- **The detector would have mis-resolved every relative path.** Both earlier rounds described the
  comparison as `realpath` + `commonpath` + `normcase` and omitted `_decide`'s actual first line —
  joining a relative path to the workspace before resolving it. `realpath` resolves a relative path
  against the *calling process's* cwd, and the two callers do not share one: `_decide` is the spawned
  MCP server, whose cwd is the run's workspace, while the detector runs in the Hub, which serves many
  projects from wherever it was started. The delta's own scenario about a `..` traversal depended on
  the missing step.
- **`.agentweave/` is not "the project's directory".** Both rounds folded it there and justified the
  `project` classification as the destination that "sits there visibly" — while the Hub writes that
  exact subtree into the repository's ignore rules on every single turn. It is the one part of the
  project root deliberately invisible to `git status`, and part of it is the Hub's own record-keeping
  about the run doing the writing. It gets its own destination kind.

The other three — the write-tool list reconciled against the wrong source, a record that would have
been lost entirely for a killed run, and a class of run for which the detector is structurally blind
— are in `design.md` under *Round 3 corrections, 2026-08-30*.

## What changes

Four parts, all decided. Nothing here re-litigates whether native mode should confine: it should not.

**(1) `Run.workspace_dir` stops implying containment.** It records where the run was *started*, and
nothing more. That is not a code change — the column already holds exactly that — it is a change to
what the product is allowed to say it means. Today `workspace-isolation` documents the workspace
namespaces and their guarantees and says nothing about what a *recorded* directory does and does not
promise, so a reader is free to conclude the wrong thing, and F71's footprinting did.

**(2) A file tool writing outside the run's workspace is detected and recorded, in every posture.**
At the **observation** path, not the approval path. Every `tool_use` block is parsed with its full
structured input to build the transcript — `runner_parsing.py:264-272` for Claude,
`codex_appserver.py:448-459` for Codex — and that parse runs regardless of posture, regardless of
whether a card was raised, and regardless of how the operator answered it. F115's escaping run was a
`Write` with an absolute `file_path`: exactly the shape this parse already sees.

**Naming is load-bearing.** The recorded fact is *a file tool wrote outside the workspace*. It is
never *"escaped"*, never *"sandbox violation"*, and never a claim about writes in general. Two vectors
are explicitly out of scope and get their own finding rather than being silently implied by a label:

- **Shell writes.** A `Bash`/`shell` call arrives as a command string, not a path argument.
  `echo x > /abs/path` is invisible to a path check on structured input.
- **Symlink traversal.** A symlink inside the workspace pointing out defeats any check on the path
  the tool reports, because that path is legitimately inside.

F115's own warning — a detector that misses the case it is about is worse than none, because it reads
as coverage — applies to the **label**, not the mechanism. Named exactly, this covers the
reproduction that produced the finding.

**The record names which workspace was written into**, using the kind-and-name vocabulary
`workspace-isolation` already requires of every reported checkout: an agent's workspace, a task's, a
review checkout, the project's own directory, or somewhere outside the project entirely. The
cross-worktree case is where that distinction carries the entire meaning.

**(3) Evidence footprinting learns about it.** Where a run wrote outside the directory its footprint
is taken from, the evidence says so rather than presenting a partial tree as complete. The footprint
itself is not moved or widened — there is no second tree to footprint against, and guessing one would
be the "silently describes another tree" failure with extra steps.

**(4) The product states plainly what confines and what does not** — and states it **per posture**,
which is the accurate form and the one the round-1 correction above forces. "Native does not confine,
Docker does" is close but not true: in native mode the `workspace` posture *does* refuse an
outside-the-workspace path per tool call, `manual` defers it to the operator, and `acceptEdits` and
full access check nothing. Docker mode confines by construction, at the mount. Saying it by mode
would tell an operator running the default posture that nothing is checking, which is false, and tell
one running full access that native mode's story applies to them, which is also false.

## Out of scope

- **Building containment.** Decided: not in this change and not by inventing a boundary. If native
  mode ever confines, it adopts an OS-level sandbox (`@anthropic-ai/sandbox-runtime`, Claude Code's
  `/sandbox`) rather than growing one here. Windows support there is alpha, needs an elevated
  install, and on Linux its deny-path mechanism only blocks files that already exist — which is
  precisely the create-a-new-file case F115 reproduced.
- **Blocking, refusing or reverting an outside write.** The operator's accepted risk, in their own
  words: work still lands in the real checkout — the operator just finds out about it.
- **Shell-command and symlink detection.** Named above, out of scope, and to be filed as their own
  finding rather than implied by this change's label.
- **Changing any posture's decisions.** `_decide` is not touched. This change observes; it does not
  approve.
