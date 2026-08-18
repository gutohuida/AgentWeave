# Exploration — Candidate names, if a rename happens (2026-08-18)

**Status:** Discussion, not a decision. Written at the operator's explicit request — `Q9-runway`
item 1 of `.claude/autonomous/STATE.json`'s queue: *"Explore names, decide nothing yet."* No name is
changed anywhere in this repository as part of writing this document, and no candidate here is
recommended over another.

This picks up where `2026-08-18-does-the-name-still-fit.md` stopped on purpose — that document
established *whether* "AgentWeave" and "Hub" still fit and priced what changing them costs, but
named zero replacement candidates ("no specific candidate proposed here, per instruction"). This
document generates candidates. It settles nothing about whether a rename should happen at all —
that question stays exactly where the prior document left it, entirely open.

---

## 1. Two directions the evidence points, not one

The two documents this is grounded in measured different things, and they pull toward different
naming directions:

- **`2026-08-18-does-the-name-still-fit.md` §1** found the shipped *architecture* — Runner/Agent/
  Charter as three separately-modeled things, a spec corpus with an archive and a `current` phase,
  `Loop` as a named recurring production unit — reads closer to **a factory floor** (stations,
  lines, a foreman reviewing output) than to a loom (strands interlacing mid-process). This is an
  architectural observation: what the product's own database schema and control flow *are shaped
  like* today.
- **`2026-08-15-where-agentweave-fits.md` §4-5** found the *market differentiation* that survived
  two weeks of competitive absorption is **durability across sessions, addressable bound identity,
  and an operator-facing UI** — not multi-agent collaboration, not spec-driven development, not
  governance, each of which a competitor now offers for free or better. This is a positioning
  observation: what makes a buyer choose AgentWeave over Claude Code's own Agent Teams, once they
  already have Claude Code.

These are not the same axis, and a name that serves one may not serve the other. "Factory" describes
what the product **is built like**; "durable, addressable infrastructure" describes what the product
**should be sold as**. A name leaning entirely into the first risks sounding like a generic
production-line tool among the many that word evokes; a name leaning entirely into the second risks
losing the concrete, inspectable, human-legible quality — you can watch a station, a foreman, a
line — that "factory" language gives the product for free. Candidates below are grouped by which
direction they lean, plus a third group that tries to gesture at both, so the split stays visible
rather than picking one implicitly by only generating candidates from one column.

## 2. Candidate names for the product

Each entry states what it signals and its most obvious cost or collision risk. None of these have
been checked against PyPI, npm, a domain registrar, or trademark records — see §4 for why that
verification is deliberately not done here.

### Factory / production-line-shaped

| Candidate | Signals | Obvious cost / risk |
|---|---|---|
| **Foreman** | The reviewing, gate-keeping role the operator already plays (review-gate, evidence, task approval) named directly as the product's core relationship to the agents doing work. | Gendered noun with no neutral equivalent in common use; "Foreman" is also an existing open-source CI/build-automation tool name in some ecosystems (unverified — flagged, not confirmed). |
| **Muster** | A roster being assembled and directed — ties to the Runner/Agent/Charter roster concept specifically, and "muster station" already carries a control/assembly connotation. | Reads more military/naval than industrial; may undersell the durable-corpus half of the product (spec documents, evidence) which "muster" says nothing about. |
| **Lineworks** | Direct "production line" imagery, `-works` suffix is a well-worn, available-feeling pattern for dev tooling (cf. "Ironworks," "Codeworks"-style names). | Generic-sounding; "line" collides conceptually with unrelated software meanings (a line of code, a product line) in a way that may dilute rather than sharpen. |
| **Depot** | A place where work accumulates and is dispatched from — matches the durable-corpus and task-board reality without being as narrow as "factory." | Already heavily used in dev tooling (package depots, artifact depots) — likely to read as generic infrastructure rather than distinctive. |

### Infrastructure / durability-shaped

| Candidate | Signals | Obvious cost / risk |
|---|---|---|
| **Ledger** | Directly names the surviving differentiator from `where-agentweave-fits.md` §4: a durable, auditable record of what agents did, across sessions. Matches the governance/evidence framing closely. | Strongly associated with accounting and blockchain/crypto in current usage — real risk of the wrong association forming before the product explains itself. |
| **Anchor** | Durability and a fixed point of reference agents' work is bound to (addressable identity) — short, easy to say, easy to alias. | Extremely common name across dev tooling already (multiple existing "Anchor" projects in blockchain, testing, and infra tooling) — high collision risk, unverified but likely. |
| **Waypoint** | Persistent, addressable checkpoints across a longer journey — echoes the Task/Loop/checkpoint shape without sounding like accounting software. | HashiCorp already ships a product named Waypoint (application deployment) — a known, likely collision, not just a guess. |
| **Continuum** | Durability across sessions as the headline claim, made abstract rather than concrete. | Abstract nouns are hard to turn into a short CLI verb or command name (`aw` already trades on brevity; "continuum" does not compress the way "weave" → `aw` did). |

### Hybrid / neither, including not renaming

| Candidate | Signals | Obvious cost / risk |
|---|---|---|
| **Keep "AgentWeave," reposition only** | Costs nothing on the six-surface table in `does-the-name-still-fit.md` §3 — no PyPI/GHCR/docs/marker migration at all. The positioning fix (`where-agentweave-fits.md` §5's actual recommendation: lead with durability/audit/addressability in messaging) does not require a name change to apply. | Leaves the "feels more like a factory now" instinct unaddressed at the naming level, only at the messaging level — the operator may find that an unsatisfying half-measure rather than a real answer. |
| **Loomworks** | A genuine hybrid: keeps the weaving root the operator is not trying to abandon ("my intention is not to drop agentweave") while adding the `-works` production-line suffix from the factory column. | Reads as a compromise-by-concatenation rather than a name someone would choose fresh: the two roots can pull against each other in a reader's ear rather than fusing into one image. |
| **Weft** | The threads that actually get woven across the loom's fixed warp — a real weaving term, not the general word "weave," so it survives the "still a loom" case from `does-the-name-still-fit.md` §2 while sounding more specific/technical than the current name. | Obscure to anyone outside textile vocabulary; trades a well-known-but-generic problem for an unknown-but-precise one, which is a real tradeoff, not a strict improvement. |

## 3. Candidate names for "Hub"

`does-the-name-still-fit.md` §4 already named the three-way structure of this decision (keep, rename
to match a factory direction, or decouple the two decisions) and priced Option 2 as "the same shape
of cost as the product rename, one layer down." That pricing is not repeated here. What follows are
candidates for Option 2 only, grouped the same way as §2 above, offered without re-arguing whether
Option 1 (keep "Hub") or Option 3 (decouple) is preferable — that choice is still open.

| Candidate | Signals | Obvious cost / risk |
|---|---|---|
| **Control Room** | Matches the operator-in-the-loop, permission-prompt, question-card reality directly — the Hub *is* where the operator watches and intervenes. | Two words; awkward as a Python package name, CLI subcommand, or directory name (`hub/` → `control-room/` or `controlroom/`, neither reads as cleanly as `hub/` does today). |
| **Floor** | Short, matches "factory floor" exactly, cheap to type. | Extremely overloaded common word — "floor" collides with UI meaning (a floor/level in a layout), price-floor idioms, and is hard to search for once shipped. |
| **Station** | A single, addressable, defined-role point in a production line — echoes Runner/Agent/Charter's own "stations with defined roles" framing from `does-the-name-still-fit.md` §1. | "Station" is already a loaded term in several adjacent ecosystems (radio/basestation infra, workstation) — moderate collision risk. |
| **Console** | Matches the operator-facing-UI framing precisely (a console is what an operator watches and issues commands from) and is a familiar, short, well-worn term in dev tooling already. | Extremely common as a generic term (browser console, admin console) — the least distinctive option in this table, trading collision risk for familiarity. |

## 4. What was deliberately not done, and why

- **No availability check.** None of the candidates above were checked against PyPI, npm, a domain
  registrar, or trademark records. Checking eight-plus candidates across four registries each is
  real, billable verification work (the kind `Q9`'s own runway note in `STATE.json` reserves for "a
  few short cheap-model turns," not a general budget) that is wasted the moment a direction narrows
  to one or two names. That check belongs *after* the operator narrows the field, not fanned out
  speculatively across every candidate here.
- **No recommendation, and no scoring.** Deliberately no weighted comparison table, no "top pick,"
  no shortlist — the operator's own framing was "explore names, decide nothing yet," and a scored
  table is a decision wearing a table's clothing.
- **No rename executed or drafted.** No file in this repository references any candidate above as a
  replacement name. `does-the-name-still-fit.md`'s six-surface cost table (product) and the
  Hub-specific pricing in its §4 both still apply unchanged to whichever candidate, if any, the
  operator eventually picks.
- **Evaluation axes worth applying later, once the field narrows, are named without being applied
  here**: pronounceability, whether a short CLI alias survives (`aw` is two letters and already
  short — does a new root offer an equally short, memorable command?), whether the word functions
  naturally as a verb an operator would actually say out loud ("open the Hub," "weave it together" —
  does the replacement support an equivalent phrase?), and collision density in the specific
  sub-industry (dev tooling / local-first agent orchestration) rather than the general English
  lexicon.

## 5. A dated document, same caveat as its source

`does-the-name-still-fit.md` §5 already flagged that any naming decision should be dated and
re-verified against the code before acting on it, because this repository's own prose has gone stale
mid-week before. The same caveat applies here with one addition: candidate availability (PyPI, npm,
domain, trademark) is **time-sensitive in a way architecture facts are not** — a name open today can
be registered by someone else before the operator returns to this document. If any candidate above
is picked up later, re-check availability at that time rather than trusting anything implied by its
absence from this list of listed risks.

The call is the operator's, exactly as asked.
