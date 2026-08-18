# Exploration — Does "AgentWeave" still fit, and what is "hub" called (2026-08-18)

**Status:** Discussion, not a decision. Written at the operator's explicit request tonight — item 9
of the autonomous queue (`.claude/autonomous/STATE.json`, `Q9-rename-exploration`), folding in the
related aside from item 2 per `decisions_for_user.N1`. No name is changed anywhere in this
repository as part of writing this document.

**Operator's framing, verbatim:** *"AgentWeave may not fit the product anymore — it feels more like
a factory now. Since we have no users yet, renaming wouldn't be too disruptive. Worth discussing."*
And, in the same breath, on item 2: *"Also open to renaming hub if there's a better term."*

This is written to be read once, cold. It answers both questions — the product name and the
"hub" term — as one decision at two scales, per the operator's own framing, with concrete costs for
each, and recommends nothing.

---

## 1. What the product actually is today, with evidence

Two documents already did real work narrowing this and neither has been revisited since:

- `2026-08-15-where-agentweave-fits.md` concluded the three differentiators claimed on
  2026-08-02 (multi-agent collaboration, spec-driven development, governance) had each been
  absorbed by the market within two weeks, and re-framed what survives as three infrastructure
  properties: **durability across sessions**, **addressable, bound identity**, and **an
  operator-facing UI** — not "multi-agent collaboration" as a headline.
- `2026-08-17-architecture-proposals.md` took that narrowed claim as given and proposed building on
  top of two shipped primitives — `Loop` (a named, purposeful, queued unit of recurring work) and
  the capability document's `current` phase (a corpus that tracks what shipped, not just what was
  proposed). Its Proposal C states plainly: *"the loop that runs this very session is not in the
  product"* — this very autonomous session, `STATE.json` and all, is architecturally the same shape
  as a `Loop`, just not represented as one yet.

Read together with what actually shipped in the six days since 2026-08-02, three things describe
where the product landed that the original name predates:

1. **Runners, Agents, and Charters are now three separately-modeled things**, not one CLI role. A
   `Runner` is reusable execution capability; an `Agent` is an addressable roster identity bound to
   at most one runner and one charter; a `Charter` is an editable behavior contract injected into
   canonical turn context (`CLAUDE.md`, "Runner, Agent, and Charter Separation"). This is closer to
   staffing and job descriptions than to threads being woven together.
2. **The spec lifecycle has an archive and a current-behaviour phase** (`exploring → proposed →
   approved → archived`, plus `current` for capability documents — `hub/hub/spec_lifecycle.py`,
   confirmed shipped 2026-08-16 by this run's own `Q8` exploration tonight,
   `2026-08-18-what-archiving-a-spec-means.md`). A corpus that accumulates a durable record of what
   shipped is a production/assembly-line concept — inputs go in, a record of finished output
   accumulates — closer to a factory's bill of materials than to weaving.
3. **`Loop` (N3, 2026-08-16) explicitly generalizes recurring, purposeful, queued work** beyond a
   single agent turn — cron-fired, with a stop condition and a `Task` board scoped to it. The
   operator's own words describing multiple loops, quoted in
   `2026-08-17-architecture-proposals.md` §"Proposal A": *"we can have loops for multiple
   things... shorter dev loops... longer loops that will do security scans."* That is a plant
   running several production lines, not threads on one loom.

None of this is a verdict. It is the evidence for why "feels more like a factory now" is not just a
mood — the roster/runner/charter separation, the durable corpus, and the loop-as-first-class-unit
are all real, shipped, load-bearing architecture, and all three are closer to a production-facility
metaphor (stations, lines, output, a record of what ran) than to a weaving metaphor (strands,
interlacing, one continuous fabric).

## 2. Does "weave" still describe it?

**The case it still fits.** The original pitch — multiple agents' work interlacing into one
coherent product — is not gone; it is still what a `Task` board, `Message`s between agents, and a
shared spec document actually do. "Weave" was always a metaphor for *combining independent threads
into one fabric*, and agents still produce independent streams of work (conversations, evidence,
runs) that a human reads as one combined picture on the Hub's dashboard. The metaphor's weakness was
never that it stopped being true; §1 above argues the *architecture* moved toward
factory/production language faster than the *name* did, not that weaving became false.

**The case it doesn't.** "Weave" implies the threads interlace with and depend on each other
mid-process — a shuttle passing back and forth, one strand aware of the next. What actually happens
today, per §1, is closer to independent stations (agents, each bound to a runner and charter)
producing independently-durable output (conversations, evidence, requirements, capability
documents) that accumulate in one place and get inspected/assembled by an operator after the fact,
not while threads are crossing. That is closer to "a factory floor with a foreman" than to "a loom."
The operator's own word choice — "factory" — names this gap directly.

**What "factory" would imply, if adopted.** A factory name would foreground: production lines
(`Loop`s) that run repeatedly and predictably; a foreman/operator role reviewing output rather than
weaving it (which the review-gate/evidence/task-approval flow already is); stations with defined
roles (`Runner`/`Agent`/`Charter`) rather than freeform collaborators; and an implicit promise of
throughput and repeatability that a weaving name doesn't carry. It would also imply less about
*collaboration between agents* (weaving's core image) and more about *repeatable production of
verified output* — which tracks §1's finding that collaboration was the differentiator the market
absorbed first, while durable, addressable, repeatable production is the one that survived.

## 3. What a rename costs, concretely

Enumerated by grepping the current tree, not estimated:

| Surface | Current name | What changing it touches |
|---|---|---|
| PyPI package (CLI) | `agentweave-ai` (`pyproject.toml:6`) | A PyPI package name is effectively permanent once published — `agentweave-ai` has shipped releases (current version `1.0.1`, `pyproject.toml:7`). Renaming means either abandoning the old name (orphaned but squattable) or keeping it as a stub that redirects, forever. |
| PyPI package (Hub) | `agentweave-hub` (`hub/pyproject.toml:6`), the CLI's sole runtime dependency (`pyproject.toml:34`) | Same permanence problem, doubled — two packages, one depending on the other by name. A rename here is also a version bump and a dependency-pin update in the same commit. |
| CLI entry points | `agentweave` and `aw` (`pyproject.toml:67-68`, both routing to `agentweave.cli:main`) | Every install instruction, every doc example, every muscle-memory the operator has typed already assumes these two commands. `aw` in particular is short enough that a different product might already hold it once the package leaves this repo's control. |
| GHCR image | `ghcr.io/gutohuida/agentweave-hub` (`hub/docker-compose.yml:12`, overridable via `AW_HUB_IMAGE`) | Docker Compose files, CI publish workflows, and any operator's local `docker-compose.override.yml` referencing the old tag all break silently until updated — a `latest` tag pointing at a renamed image doesn't just 404, it stops receiving new pushes with no local error until someone notices staleness. |
| Docs site | `site_name: AgentWeave`, `site_url: https://gutohuida.github.io/AgentWeave/`, `repo_url: .../AgentWeave` (`mkdocs.yml:1,4,6`) | The GitHub Pages URL is derived from the **repository name**, not just the mkdocs config — renaming the docs site name alone leaves the URL pointing at the old repo name unless the GitHub repo itself is also renamed (GitHub does auto-redirect old repo URLs after a rename, but forks/clones/bookmarks/CI badges referencing the old URL keep working only via that redirect, not natively). |
| `.agentweave/` marker directory | `AGENTWEAVE_DIR = Path(".agentweave")` (`src/agentweave/constants.py:8`), with every other path (`AGENTS_DIR`, `TASKS_DIR`, `LOGS_DIR`, `SESSION_FILE`, `TRANSPORT_CONFIG_FILE`, `AGENT_CONTEXT_DIR`, …) derived from it | This is a **per-project on-disk marker**, not just a repo-internal constant — `CLAUDE.md` describes it as binding a project ID to this machine's database. Renaming it means every project ever registered with the old marker name needs a migration path (detect old marker, offer to rename/re-register) or silently orphans every existing registration, including this repo's own `proj-5e960453`. |
| `CLAUDE.md` itself | References "AgentWeave" as the product name and "Hub" as a proper noun throughout (`grep -c` puts the count over 100 across headers, prose, and code comments) | The governing instruction file for this very repository's agent-assisted development would need a full pass, not a find-replace — several sentences use "the Hub" as a specific proper-noun referent to the FastAPI+React service (e.g. "Point the Hub you are editing at this repo") that a bare find-replace of the word "hub" would corrupt if the term itself is also being renamed (see §4). |
| In-repo prose generally | "AgentWeave"/"agentweave" appears in `README.md`, every `openspec/` document, UI copy (window title, page titles), the pywebview window title (`cli.py:752`), and the just-shipped taskbar icon's mark (Q7 tonight) | The taskbar icon shipped *tonight* under the current name — not a blocker, since the mark itself is a woven-ribbon geometric motif that doesn't spell out the word, but worth naming: a rename decided soon would mean the icon's motif choice (chosen to evoke "weave") is worth re-examining alongside the name, not after. |

**What "no users yet" actually buys.** The operator's stated reasoning — *"we have no users yet, so
renaming wouldn't be too disruptive"* — is true for the *external* surfaces (nobody has a bookmarked
doc URL, a pinned Docker tag, or muscle memory for `aw` yet, except the operator). It does **not**
reduce the cost of the *internal* surfaces: the `.agentweave/` marker rename still needs a migration
path for this repository's own registered projects (this repo, the trial Hub's fixtures, any other
local registrations), and the PyPI/GHCR name-permanence problem exists the moment a name is
published regardless of how many people installed it — `agentweave-ai` and `agentweave-hub` are
already published at `1.0.1`. "No users" lowers the *social* cost of a rename close to zero; it does
not lower the *mechanical* cost, which is the same list of six surfaces above either way.

## 4. Options for the "hub" term

The operator's aside is a narrower, second-order version of the same question: does "Hub" still
describe the FastAPI + React service that owns execution, or did it also drift?

**What "Hub" currently means, precisely** (per `CLAUDE.md`'s own architecture section): a single
local instance that owns a *collection of projects*, orchestrates agent runs, serves the dashboard,
and is the *only* runtime — CLI commands do "only what cannot be done from inside the app: start it,
diagnose why it will not start, stop it, reset it." "Hub" as a word implies a central point many
spokes connect to — which is accurate for the *multi-project* fact (one Hub, many registered
projects) but says nothing about the *execution* fact (it also runs agents, stores specs, gates
evidence) that "Hub" alone doesn't capture.

**Option 1 — keep "Hub."** It is short, already used as a proper noun in >100 places in `CLAUDE.md`
alone, matches the literal multi-project topology (one instance, many projects registered against
it), and — unlike the product name — has comparatively low external cost, since "hub" is a common
noun used descriptively (`hub/` the directory, `Hub` the FastAPI app) rather than a trademarked
product name published to a registry. The main cost of keeping it is definitional drift: the word
undersells what the service actually does (execution + orchestration + storage + UI), not just
routing.

**Option 2 — rename to something execution/production-shaped**, to match a factory reframing of the
product name if that direction is chosen (e.g. a term evoking a control room, a floor, a plant, a
foreman's station — no specific candidate proposed here, per instruction). Cost: `hub/` is a
top-level directory name, a Python package (`hub.main:app`, `hub.main:run` in
`hub/pyproject.toml:31`), the PyPI package `agentweave-hub`, the GHCR image
`ghcr.io/gutohuida/agentweave-hub`, and the term "Hub" recurs as a specific proper noun through every
architecture doc in this repo, `openspec/`, and the UI itself (page chrome, `hub/ui/`). It is the
same shape of cost as the product rename, one layer down, and inherits the same
`.agentweave/`-marker migration problem if the CLI-facing vocabulary changes with it (e.g. `hub
start` in prose/help text).

**Option 3 — decouple the two decisions entirely.** Rename the product without renaming "Hub" (the
Hub becomes "AgentWeave's Hub" under whatever new product name, unchanged internally), or vice
versa. Cost: lower per-decision, but risks the exact half-migrated state `CLAUDE.md`'s own opening
section already warns against for the openspec-to-AgentWeave-spec migration — a partially-renamed
product reads as unfinished rather than deliberate, and doubles the number of times prose,
onboarding docs, and the operator's own habit need to resettle.

None of these three is recommended over another here, per instruction.

## 5. A dated, re-verifiable decision, not a settled one

Worth stating plainly, because this run's own `Q8` exploration tonight found it the hard way:
**`CLAUDE.md`'s own prose about the product has already gone stale at least once this week** — the
"no archive phase" claim in its Specifications section was true when written and false by the time
this session read it, because the archive phase shipped 2026-08-16 without the file being updated
(`2026-08-18-what-archiving-a-spec-means.md`, opening finding). A naming decision, whenever it is
made, should be **dated and re-verified against the code before anyone acts on it** — not treated as
permanently settled the moment it's decided, the same way "no archive phase" was treated as settled
prose long after it stopped being true. If the operator picks a direction from this document next
week, the six-surface cost table in §3 is worth re-running against the tree at that time rather than
assumed unchanged, in case something else shipped a seventh surface in the interim.

## What this document does not do

- **Does not propose a new name.** Neither for the product nor for "Hub."
- **Does not touch any file, string, or asset that spells out the current names.** No rename, no
  find-replace, no icon change.
- **Does not decide whether "factory" is the right replacement metaphor** — only that the operator's
  instinct has real, cited architectural evidence behind it (§1), which is different from confirming
  the specific word "factory" is the answer.

The call is the operator's, exactly as asked.
