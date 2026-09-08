# Third review — the four unapproved changes, 2026-09-08

Run by an Opus subagent at the operator's instruction, briefed to work **blind**: it did not open
`second-review-2026-09-08.md` or `handoff-0114` until its own findings were written, then reconciled
against them. Read-only throughout — it edited nothing, wrote no verdict token, started no Hub.

Unlike the two rounds before it, **this one measured the F295 arrangement** rather than reading it.

**Verdict: none of the four needs another round.** One finding blocks implementation of change 4 and
has been repaired; six more were editorial and have been repaired; two are recorded for the operator
and the drive.

---

## Findings, and what was done with each

### R-1 — *Blocked implementation.* Change 4's task 2.2 had the ordering backwards. **Repaired.**

`tasks.md` §2.2 read: *"Pass the run's access path through at the injection site,
`agents.py:1543`. The path is already resolved for the run at `agent_trigger.py:1006`; the context
materialisation must receive it."*

**The materialisation happens 46 lines before the resolution.** Verified independently:

- `agent_trigger.py:960` — `rendered_context = await _render_hub_agent_context(...)`
- `agent_trigger.py:1006` — `access_path = resolve_access_path(runner, probe["cli"] or agent, ...)`

There is nothing to receive at `:960`; the value does not exist yet. A task whose own justification
is about two things agreeing got their order wrong, in a change the second review certified as
needing no repair.

Two further gaps in the same task, both confirmed:

- **The hoist is available and needed to be stated.** `config` is bound at `agent_trigger.py:640`,
  `probe` at `:647`, `runner` at `:648` — all far above `:960` — so `resolve_access_path` can move
  above the materialisation and its one value be reused at `:1006`.
- **`_render_hub_agent_context` has three production callers, not one**: `agents.py:1769`,
  `agents.py:2143`, `agent_trigger.py:960`. §2.1 protects `_tool_surface_lines`' call sites with an
  MCP default; §2.2 said nothing equivalent. A `GET .../context` route left rendering MCP wording
  for an agent whose next run takes the HTTP path reintroduces exactly the disagreement §2.2 exists
  to prevent.

§2.2 has been rewritten to say all three things.

### R-2 — Change 1 task 1.5 named two attributes without naming their object. **Repaired.**

1.5 said *"sets `_running = False` and `_connection = None`"*. Those belong to the **inner**
`aiosqlite.Connection` (`dbapi_connection._connection`), not to the `AsyncAdapt_aiosqlite_connection`
the listener is handed — and `design.md`'s two quotations are of the inner class without saying so.
A literal misreading fails loudly rather than silently (the adapter's `__slots__` does not carry
them), but the task should not require an implementer to discover that. Now named explicitly.

### R-3 — The aiosqlite line drift had **three** instances, not two. **Repaired.**

The second review's S-2 enumerated `design.md:66`, `:69` and `tasks.md` 1.3, and repaired those.
`proposal.md:65` still said `core.py:199-201`. Corrected to `:202-203`. Low risk — 1.3 is the task
that writes the number into a source comment and 1.3 was already right — but it is the surviving
instance of a drift reported as fully repaired.

### R-4 — The delta says "every path" and the tasks build four of five. **Recorded as task 1.6 — the operator may drop it.**

`specs/app-lifecycle/spec.md`: *"Putting it beyond use SHALL cover **every path** that closes such a
connection."* Tasks 1.1–1.5 enumerate four, all downstream of `_ConnectionRecord.__close()`, which
dispatches `close` (`sqlalchemy/pool/base.py:880-881`). There is a fifth: `_finalize_fairy` closes a
**detached** connection through `pool/base.py:999-1000`, which dispatches `close_detached` — a
different event a `close`-only listener never sees.

**Measured not reachable today**: `grep -rn "\.detach()" hub/hub/ --include=*.py` returns nothing,
and the probe's `close_detached` counter fired zero times across checkout invalidation and dispose.
So this is a requirement overstating what the tasks build, not a hole in the fix. Both honest
repairs are stated in the new task 1.6 — write the two lines, or narrow the requirement — and the
choice is left to the operator because it is the one repair in this round that adds scope.

### R-5 — Change 2 task 1.2 needs an import it did not name. **Repaired.**

`Run` is not imported in `agent_chat.py`; its `from ...db.models import (...)` block at `:36-47`
names ten symbols and not that one. One line, but this is a change whose tasks otherwise name every
file, symbol and line number they touch.

### R-6 — Change 2 task 1.5's "factor the construction" was vacuous or contradictory. **Repaired.**

Read one way it has no work to do (1.2's single helper means there is only ever one construction);
read the other way — factor with `agents.py:830-841` — it contradicts `proposal.md`'s Impact line
*"No server code outside `agent_chat.py`"*. Now says which: do not factor across the two modules,
and why the duplication is accepted.

### R-8 — Change 3 never said where the dialog mounts. **Repaired as a new task 1.4.**

`InstructionsPage` returns a single `<SettingsSection>`; Save lives in the `actions` prop
(`:62-69`), which renders in the section's heading as a **sibling** of `{children}` (`:71-152`).
Task 2.3 forbids moving Save. So the dialog has to mount inside the `data` branch of `{children}`
or the return has to be wrapped in a fragment — and no task said so. It also decides
`useDialogFocus`'s focus restoration to a control in the other subtree.

### R-7 — Change 2's D9 records the indicator's narrowing but not its widening. **Recorded, not repaired.**

`anotherRunIsUnderway` (`AgentTimeline.tsx:166-172`) scans the whole `runs` map. Today that map is
capped by the timeline route's fifty events (`agents.py:802-803`); afterwards it holds every run
named by an **unbounded** conversation's entries. So a single old run row still reading non-terminal
in this conversation could light the indicator for the life of the conversation whenever `isRunning`
is true. `reconcile_interrupted_runs` makes such rows rare and `isRunning` gates the visible effect.

**Deliberately not written into `design.md`: the reviewer rated it low confidence and did not
measure it.** Task 6.7 already drives the indicator live; this is what that drive should also watch
for. Recording an unmeasured claim in a design document is how a later round inherits it as
evidence.

### R-9 — Change 4's `test_launchability.py` citations sit ~2 lines early. **Not repaired.**

`TestAccessPath` is at `:392` and the task cites the range `:390-429`, which brackets the class
correctly; the individual test line numbers drift by two. Every claim *about* those tests was
confirmed correct. Cosmetic, and repairing a bracketing range that already contains its subject adds
churn without adding accuracy.

### R-10 — The two bundle-touching changes collide only in the generated artefact. **Already recorded.**

Independently reached the same conclusion as the second review's S-3, and sharpened it: changes 2
and 3 share no source file, so sequential landing is fine and only parallel branches conflict — in
minified output, which is unmergeable. Already written into `APPROVALS.md` and `ROADMAP.md`.

---

## What this round measured that neither earlier round did

The F295 arrangement was **built and run**, not read. Against a lookalike `create_async_engine` on a
temp file with `AsyncAdaptedQueuePool`, killing a pooled worker by the real mechanism:

```
pool=AsyncAdaptedQueuePool worker alive after kill: False
A checkout: RECOVERED select 2 -> 2 in 0.00s
B second worker alive after kill: False
B dispose: returned in 0.00s
fires: {'checkout': 1, 'close': 2, 'close_detached': 0, 'connect': 2}
```

Without the `close` listener the same checkout **did not return** — it survived an
`asyncio.timeout(20)` and ran roughly seven minutes to a manual kill. That independently reproduces
both `design.md`'s "bound the wait — rejected" result and R3's dispose-hang, and it confirms R3's
central correction on a probe written from scratch rather than on the deleted ones.

Three things it established that no round had:

- **`QueuePool.recreate()` passes `_dispatch=self.dispatch`** (`pool/impl.py:203-218`), so the
  listeners survive the pool replacement `Engine.dispose()` performs. A hazard nobody had raised,
  closed by construction.
- **The invalidate path closes with `terminate=True`** → `do_terminate` → `AsyncAdapt_terminate` →
  `await_(shield(self._connection.close()))` (`connectors/asyncio.py:397-415`), a *different* code
  path from `dispose()`'s `do_close`. The neutralisation covers both because both are downstream of
  the same `close` dispatch.
- **`PoolEvents._accept_with` refuses an `AsyncEngine`** (`pool/events.py:84`), which is why
  `engine.sync_engine` is the correct listener target rather than a stylistic choice.

---

## Correction to the second review

**Its file-handle claim was right, and stated more confidently than its evidence supported.** It
wrote that clearing `_connection` *"drops the last reference to the underlying `sqlite3.Connection`
and refcounting closes it. The neutralisation leaks no file handle"*, in a passage framed as read
directly from the library. The conclusion is correct — this round **measured** it, and `os.remove`
on the database file succeeds after the neutralisation and dispose, so no OS handle is held — but
reading `_conn`'s property definition does not establish it. `_tx` can still hold `partial`s bound
to the same `sqlite3.Connection`; whether the whole graph becomes garbage is a refcount question,
not a property-definition question.

The correction that matters is about method, not about the fact. It was the second review's only
measured-sounding claim that was reasoned, and this repository's stated failure mode is an argument
that is wrong while everything it argues about is right.

**Its other structural miss:** it re-derived the load-bearing claims from the code and added four new
classes of check, but never asked *would an implementer following this task literally produce the
thing the spec requires*. R-1 is exactly what that question finds, and it was sitting in a change the
second review certified as needing no repair.

---

## What this round did not do

- **Started no Hub, drove nothing.** `:8000` and `:8010` were not contacted.
- **Ran no test suite, no lint, no type-check, no build.** Nothing here says any of the four *works*.
- **Its probes are standalone scripts, not the product's engine.** A lookalike `create_async_engine`
  on a temp file with listeners of the specified shape — not `hub.db.engine`, not a running Hub. The
  `F296` gap is unchanged.
- **Did not run `conftest.py`'s cap-skips-dispose path** — still the one unmeasured link under
  change 1's "where the damage is demonstrated" paragraph, as R3 said.
- **Did not verify change 4's two named drive questions**: that an HTTP request carrying
  `AW_RUN_TOKEN` succeeds from inside a spawned run's environment, and what Claude does when
  `--permission-prompt-tool` names an absent MCP tool. `tasks.md` §6.3/§6.5 still own them.
- **R-7 is reasoned, not measured.**
