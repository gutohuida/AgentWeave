# Derivation heuristics

Each heuristic turns an observation about *this* repository into a specific proposal. Every one
names what to look for, what it becomes, and — importantly — when **not** to fire.

The discipline that makes this work: a heuristic that matches produces a proposal citing the
matching line. A heuristic that does not match produces nothing. Do not fill gaps with defaults.

---

## H1 — Absolutes that cannot be enforced

**Look for:** lines in instruction files containing `NEVER`, `ALWAYS`, `ALL <x> must`, `must
not`, `without exception`, `under no circumstances`, or an imperative paired with a mechanical
trigger ("before committing", "after every edit", "on every save").

**Test:** could a script decide, from the tool call alone, whether the rule was violated?

- **Yes → hook.** Name the event and the matcher. Blocking rules are `PreToolUse` with exit 2.
  Post-hoc corrections are `PostToolUse`. Pre-submission gates are `Stop`.
- **Yes, and it is purely file or command access → permission rule.** Prefer this over a hook
  when it fits: it is declarative, needs no script, and works on every platform. `deny` beats a
  `PreToolUse` script for "never read `.env`".
- **No, it needs judgment → leave it as an instruction**, and say so. "Prefer composition over
  inheritance" is correctly a request. Not every absolute wants to be a hook.

**Do not fire when:** the rule is aspirational, or the enforcement would produce false positives
that block legitimate work. A hook that cries wolf gets disabled, and then the rule has neither
enforcement nor visibility.

**Report as:** `<file>:<line> "<quoted rule>" → PreToolUse hook, matcher <Tool>, blocks when
<condition>`.

---

## H2 — Content the agent can derive

**Look for:** directory trees, file listings, dependency inventories, architecture overviews,
API surface dumps, generated tables of contents.

**Why it costs twice:** it is paid on every request, and it goes stale silently — nothing fails
when the tree changes, so it quietly starts lying.

**Becomes:** deleted. Keep only what the codebase does *not* say: pitfalls, rationale, decisions
that differ from the tool's defaults, and the reason a surprising thing is the way it is.

**Delegate:** if the running harness ships `/doctor`, it already proposes this trim with the
same heuristic. Say so and hand off rather than reimplementing. Reserve your own analysis for
the parts `/doctor` does not cover.

**Do not fire when:** the structure is genuinely non-obvious and expensive to rediscover — a
layout that contradicts convention, or a monorepo boundary that matters. One paragraph of
"where things live, and why it is not where you'd expect" earns its place. Ten lines of `tree`
output do not.

---

## H3 — Sometimes-content charged always

**Look for:** instruction sections that only apply inside one directory, one language, one
subsystem. Signals: a heading naming a path, guidance that references files under a single
subtree, or a section a reader would skip unless working in that area.

**Becomes:** `.claude/rules/<topic>.md` with `paths:` frontmatter.

**Always state the trade-off.** Path-scoped rules are **lost after compaction** until a matching
file is read again. Root instruction files and unscoped rules are re-injected from disk. So:

| The rule is | Put it |
|---|---|
| Useful guidance for one area | Path-scoped — take the context saving |
| An invariant that must hold in hour six of a long session | Unscoped, or a hook |
| A safety boundary | A hook or a permission rule; not a rule file at all |

**Do not fire when:** the section is under ~10 lines. The frontmatter, the extra file, and the
reader's cost of chasing it exceed the saving.

---

## H4 — Procedures in a facts file

**Look for:** numbered steps, "first… then…", checklists, anything a person would follow rather
than know. A heading like "Adding a CLI command" followed by four steps is the archetype.

**Becomes:** a skill. Add `disable-model-invocation: true` if it has side effects or if you want
to control when it fires — that also drops its context cost to zero until invoked.

**Do not fire when:** it is two steps and both are commands. A `make test` line is a fact.

---

## H5 — Context floods

**Look for:** recurring operations that emit far more output than the decision they inform —
full test-suite runs, log tailing, dependency audits, broad searches, build output.

**Becomes**, in preference order:

1. A `PreToolUse` hook that **rewrites** the command to filter before the output is ever seen.
   Cheapest, deterministic, and works even when the agent forgets. Filtering a test run to just
   failures turns tens of thousands of tokens into hundreds.
2. A subagent, when the work needs judgment rather than a fixed filter.
3. A note in the instruction file, only if neither fits.

**Do not fire when:** you need to read the full output to steer. Isolation costs you visibility.

---

## H6 — The build is not wired up

**Look for:** a formatter, linter, or type-checker that the repo clearly uses (config file
present, CI runs it, the instruction file mentions it) but which nothing runs automatically
after edits.

**Becomes:** a `PostToolUse` hook on `Write|Edit`. Its output feeds back to the agent, so
mistakes get caught inside the turn instead of in CI.

**Do not fire when:** the tool is slow enough that running it per-edit would dominate the loop,
or when the repo deliberately batches it. Check for an existing pre-commit hook first — if one
exists, propose alignment, not duplication.

---

## H7 — Permission friction, and permission over-reach

Two directions, both worth checking.

**Friction:** the same operations get approved repeatedly. Becomes a scoped allowlist in
`.claude/settings.json` so the whole team benefits. If the harness ships
`/fewer-permission-prompts`, it generates this from real transcripts — delegate.

**Over-reach:** a blanket bypass (`defaultMode: bypassPermissions`, `--dangerously-skip-permissions`,
a permission mode that skips prompts entirely). This is a legitimate choice and many people make
it deliberately — do not moralise. State it as a finding once, show the narrower allowlist that
would cover the observed workflow, mention auto mode and sandboxing as middle grounds, and let
the user decide. Do not change it without explicit confirmation; it is Tier 2 and it is the
single most disruptive thing in this skill.

---

## H8 — Orphans and drift

**Look for:**
- skills whose descriptions load every session and which nothing invokes
- MCP servers configured but unused in this repo's workflow
- rules or instruction sections that contradict each other
- instruction content describing code that no longer exists
- `.claude/commands/*.md` alongside `.claude/skills/` — both work, but split conventions drift
- scratch and handoff directories not covered by `.gitignore`

**Becomes:** removal, consolidation, or a `disable-model-invocation: true` flag. Contradictions
are the worst of these — when two rules conflict, the agent picks one arbitrarily, so a
contradiction is strictly worse than either rule alone.

---

## H9 — Delegation opportunities

**Look for:** repeated spawning of the same kind of worker with the same instructions, or
verbose specialised work done inline.

**Becomes:** a subagent definition in `.claude/agents/`. Pin a cheaper model where the work does
not need the expensive one; preload the skills it always needs via `skills:`; restrict `tools:`
to what it should be able to do.

**Do not fire when:** there is only one kind of task and it is already fine inline. Subagent
definitions nobody uses are H8 material next audit.

---

## Ranking

Order the report by impact, computed roughly as:

1. **Invariants made enforceable** — a rule that was being violated is worth more than any
   number of saved tokens.
2. **Tokens saved per request** — always-on cost removed, multiplied by every request forever.
3. **Feedback loops shortened** — verification wired up, output filtered at the source.
4. **Friction removed** — prompts, repeated corrections.
5. **Hygiene** — orphans, drift, gitignore.

A single H1 finding usually outranks every H2 finding combined. Say so when it does.
