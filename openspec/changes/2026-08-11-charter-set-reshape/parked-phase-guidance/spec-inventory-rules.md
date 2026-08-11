# Parked: the spec charter's `spec/` inventory rules

> Cut verbatim from `hub/hub/data/charters/spec.md` (lines 7–9, 28–33, 49–52, 73 of the pre-change
> file) by `2026-08-11-charter-set-reshape`, task 2.6. Reference material only — nothing loads this
> file.
>
> **Why it was cut:** a Hub-owned project has no `spec/` tree — `CLAUDE.md` forbids creating one at
> a repository root, and nothing in the Hub creates one for a project. The inventory rule also
> carries a false claim about the Hub's behaviour (see the warning inline below).
>
> **What it is waiting on:** a phase-guidance mechanism, and a spec on-ramp that decides where
> specification documents actually live. The judgment worth keeping here is the "one root" rule —
> writing into two trees is a real failure mode independent of which tree it is.

---

## ⚠️ One clause below is factually wrong and must not be reinstated as written

> "The Hub discovers every safe `spec/**/*.html` file independently of `spec/index.json`"

The Hub performs no such discovery. `hub/hub/api/v1/spec.py:71,213` stores an inventory a *client*
supplies as `discovered_paths`. The rglob is in `src/agentweave/spec_manifest.py:90`, on the CLI
side — reachable only from the skills that no longer install. If this text is ever picked up, that
sentence has to go or become true first.

---

## From "You Are Responsible For"

- Owning the durable spec layer under `spec/`: the system map (`spec/system-map.html`), epic roadmaps
  (`spec/roadmaps/*.html`), and the living behavioral spec (`spec/*.html`)
- Owning per-change specs (`spec/changes/<name>/spec.html` when that workflow is in use)

## From "On session start"

2. Inventory `spec/` before assuming a path — it is the single spec root. The Hub
   discovers every safe `spec/**/*.html` file independently of `spec/index.json`, so a document
   missing from the manifest is still visible (reported as drift), not lost. Read the system map
   and living spec first, then the relevant active change specs. If a project still keeps specs
   elsewhere (e.g. a legacy `specs/`), say so and agree one root with the user rather than writing
   into two trees

## From "When the user asks for spec changes (e.g. via the Hub Spec tab)"

- Edit the spec file in place, then regenerate the complete HTML file — never leave it half-broken or partially updated
- Keep `<meta name="aw-spec-status">`, the TOC, and all anchors consistent after regeneration
- Reply with a short changelog of what changed

## From "Anti-Patterns"

- Editing only part of the HTML and leaving the file broken — always regenerate the complete, valid file
- Writing specs into a second tree (`specs/`, a stray `spec/specs/`) — `spec/` is the one root
