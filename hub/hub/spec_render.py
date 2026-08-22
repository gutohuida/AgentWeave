"""Rendering a validated payload into the document an operator reads.

The agent never writes this markup. That is what retires the 713-line format
contract: escaping, anchors, metadata and section order stop being things a
model is asked to get right and become things it cannot get wrong.

Two consequences worth stating, because they look like omissions:

**Anchors cannot dangle and identifiers cannot collide.** Every anchor is
emitted from the same minted identifier that the link is emitted from, so the
old self-check for dead anchors and duplicate ids has nothing left to find.

**The document carries no navigation script.** The shell injects the bridge into
the frame (`specBridge.withSpecBridge`), so a same-document anchor interceptor
written here would be a second, divergent copy of something the shell already
owns. The renderer's job stops at semantic structure with stable ids.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from .spec_payload import SpecPayload, embed_payload

# Three layers, in this order: variables, the system preference, and an explicit
# override the shell can set. A document that honoured only the media query
# would fight a shell whose theme was chosen rather than inherited.
#
# The six neutral custom properties (--bg/--fg/--muted/--border/--surface-2/--surface)
# are named to match SpecFrame.tsx's theme override (HUB_NEUTRALS) so the shell's
# inherited values actually land on something the document reads. --aw-accent is
# deliberately unprefixed-but-unmatched: it stays the document's own literal, per
# SpecFrame.tsx's own comment that accent/warn/done/danger are not the Hub's to recolour.
_STYLE = """
:root {
  --bg: #ffffff; --fg: #1f2328; --muted: #656d76; --border: #d8dee4;
  --aw-accent: #0969da; --aw-warn: #9a6700; --aw-ok: #1a7f37;
  --surface-2: #eaeef2; --surface: #f6f8fa;
  --aw-dur-fast: 150ms; --aw-dur-base: 250ms; --aw-ease: cubic-bezier(0.16, 1, 0.3, 1);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --border: #30363d;
    --aw-accent: #4493f8; --aw-warn: #d29922; --aw-ok: #3fb950;
    --surface-2: #21262d; --surface: #161b22;
  }
}
:root[data-theme="light"] {
  --bg: #ffffff; --fg: #1f2328; --muted: #656d76; --border: #d8dee4;
  --aw-accent: #0969da; --aw-warn: #9a6700; --aw-ok: #1a7f37;
  --surface-2: #eaeef2; --surface: #f6f8fa;
}
:root[data-theme="dark"] {
  --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --border: #30363d;
  --aw-accent: #4493f8; --aw-warn: #d29922; --aw-ok: #3fb950;
  --surface-2: #21262d; --surface: #161b22;
}
* { box-sizing: border-box; }
@media (prefers-reduced-motion: reduce) {
  :root { --aw-dur-fast: 0ms; --aw-dur-base: 0ms; }
}
body {
  margin: 0; padding: 2rem 2.5rem 4rem; background: var(--bg); color: var(--fg);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
h1 { font-size: 1.75rem; margin: 0 0 .25rem; }
h2 { font-size: 1.15rem; margin: 2.5rem 0 .75rem; padding-bottom: .3rem;
     border-bottom: 1px solid var(--border); }
h3 { font-size: 1rem; margin: 1.5rem 0 .4rem; }
p { margin: .5rem 0; }
ul, ol { margin: .5rem 0; padding-left: 1.4rem; }
li { margin: .25rem 0; }
a { color: var(--aw-accent); }
.aw-meta { color: var(--muted); font-size: .85rem; margin: 0 0 1.5rem; }
.aw-nav { font-size: .85rem; margin: 0 0 1.5rem; }
.aw-nav a + a::before { content: "›"; color: var(--muted); margin: 0 .6rem; }
.aw-map-list { list-style: none; margin: .5rem 0; padding-left: 0; }
.aw-map-list .aw-map-list { padding-left: 1.25rem; margin-top: .5rem; }
.aw-map-item { margin: 0; padding: .75rem .35rem; border-bottom: 1px solid var(--border);
               transition: background var(--aw-dur-fast) var(--aw-ease); }
.aw-map-item:hover { background: var(--surface); }
.aw-map-item:last-child { border-bottom: 0; }
.aw-map-item > p { margin: .2rem 0; }
.aw-chip { display: inline-block; padding: .1rem .5rem; border-radius: 999px;
           background: var(--surface-2); font-size: .78rem; margin-right: .4rem; }
.aw-requirement { border: 1px solid var(--border); border-left: 3px solid var(--border);
                  border-radius: 6px; padding: .8rem .9rem; margin: .75rem 0;
                  transition: background var(--aw-dur-fast) var(--aw-ease),
                              border-color var(--aw-dur-fast) var(--aw-ease); }
.aw-requirement:hover { background: var(--surface); }
.aw-requirement-must { border-left-color: var(--aw-accent); }
.aw-requirement-should { border-left-color: var(--aw-warn); }
.aw-requirement-may { border-left-color: var(--border); }
.aw-id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .8rem;
         color: var(--muted); }
.aw-modal { display: inline-block; padding: .05rem .42rem; border-radius: 999px; font-size: .75rem;
            font-weight: 650; letter-spacing: .02em; }
.aw-modal-must { color: var(--aw-accent); background: color-mix(in srgb, var(--aw-accent) 12%, var(--bg)); }
.aw-modal-should { color: var(--aw-warn); background: color-mix(in srgb, var(--aw-warn) 12%, var(--bg)); }
.aw-modal-may { color: var(--fg); background: var(--surface-2); font-weight: 500; }
.aw-chip-rigor-gate { color: var(--aw-accent); border: 1px solid var(--aw-accent); }
.aw-chip-rigor-contract { color: var(--aw-warn); border: 1px solid var(--aw-warn); }
/* Phase is a lifecycle, and the question it answers is "can I rely on this?". `approved` and a
   capability's `current` are settled and take the done tone; `proposed` is waiting on an operator
   decision and takes warn; `exploring` and `archived` are quiet for opposite reasons — one has not
   arrived yet, the other has been superseded. Deliberately NOT the accent: this document already
   spends accent on links and on MUST, and a third meaning would empty it of any. `kind` keeps the
   plain chip on purpose — it is a category, not a state, and hue there ranks nothing. */
.aw-chip-phase-done { color: var(--aw-ok); border: 1px solid var(--aw-ok); }
.aw-chip-phase-waiting { color: var(--aw-warn); border: 1px solid var(--aw-warn); }
.aw-chip-phase-quiet { color: var(--muted); }
.aw-chip-phase-archived { color: var(--muted); text-decoration: line-through; }
/* An unresolved question blocks `propose`, so it is a real state and not a label. Resolved stays
   the plain chip — the reader needs to find what is still open, not celebrate what is closed. */
.aw-chip-open { color: var(--aw-warn); border: 1px solid var(--aw-warn); }
/* Limits is where a reader is most likely to be misled, and it read identically to Checked. */
.aw-limits { color: var(--aw-warn); }
/* The first screenful was entirely monochrome, so the document read as texty however the
   requirements below were coloured. This puts the same modal scheme where the eye lands first,
   carrying counts rather than decoration. */
.aw-summary { margin: 0 0 1.5rem; padding: .65rem .8rem; border: 1px solid var(--border);
              border-radius: 6px; background: var(--surface); font-size: .9rem; color: var(--muted); }
.aw-summary .aw-count { font-weight: 600; }
.aw-summary-sep { color: var(--border); margin: 0 .45rem; }
.aw-position { float: right; color: var(--muted); font-size: .72rem; text-transform: uppercase;
               letter-spacing: .05em; }
.aw-anchor-copy { margin-left: .35rem; padding: .1rem .3rem; border: 1px solid transparent;
                  border-radius: 4px; background: transparent; color: var(--muted); cursor: pointer; }
.aw-anchor-copy:hover { border-color: var(--border); color: var(--aw-accent); }
.aw-anchor-copy:focus-visible, a:focus-visible { outline: 2px solid var(--aw-accent); outline-offset: 2px; }
.aw-rationale { margin-top: .7rem; padding-left: .7rem; border-left: 2px solid var(--border);
                color: var(--muted); font-size: .9rem; }
.aw-rationale-label { display: block; margin-bottom: .15rem; font-size: .68rem; font-weight: 650;
                      letter-spacing: .08em; text-transform: uppercase; }
.aw-refs { font-size: .82rem; color: var(--muted); }
.aw-note { color: var(--muted); font-style: italic; }
.aw-empty { color: var(--muted); }
table { border-collapse: collapse; margin: .75rem 0; width: 100%; }
th, td { border: 1px solid var(--border); padding: .4rem .6rem; text-align: left;
         vertical-align: top; font-size: .92rem; }
tbody tr { transition: background var(--aw-dur-fast) var(--aw-ease); }
tbody tr:hover { background: var(--surface); }
tbody tr[data-first="true"] td { border-top: 2px solid var(--aw-accent); }
.aw-cell-empty { color: var(--muted); text-align: center; }
.aw-task-list { list-style: none; padding-left: 0; }
.aw-task { margin: .5rem 0; padding: .65rem .75rem; border: 1px solid var(--border);
           border-radius: 6px; background: var(--surface); }
.aw-task .aw-refs { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .35rem; }
code, pre { background: var(--surface); border-radius: 4px; }
code { padding: .1rem .3rem; font-size: .88em; }
""".strip()

def _e(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def _paragraphs(text: str) -> str:
    blocks = [block.strip() for block in (text or "").split("\n\n") if block.strip()]
    return "".join(f"<p>{_e(block)}</p>" for block in blocks)


def _section(title: str, anchor: str, body: str) -> str:
    if not body:
        return ""
    return f'<section id="{anchor}"><h2>{_e(title)}</h2>{body}</section>'


def _list(items: List[str], empty: str = "") -> str:
    if not items:
        return f'<p class="aw-empty">{_e(empty)}</p>' if empty else ""
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ul>"


# MUST/SHALL carry equal weight in RFC2119 language, so both take the "must" tone. Unknown
# values (should not occur — spec_payload.py's MODALS validates on the way in) fall back to
# "may", the tone that adds no colour, rather than raising here.
_MODAL_TONE = {"MUST": "must", "SHALL": "must", "SHOULD": "should", "MAY": "may"}


def _requirements(payload: SpecPayload, identifiers: Dict[str, str]) -> str:
    if not payload.requirements:
        return '<p class="aw-empty">No requirements yet.</p>'
    parts: List[str] = []
    total = len(payload.requirements)
    for index, requirement in enumerate(payload.requirements, start=1):
        identifier = identifiers.get(requirement.key, "")
        tone = _MODAL_TONE.get(requirement.modal, "may")
        party = f'<span class="aw-chip">{_e(requirement.party)}</span>' if requirement.party else ""
        rationale = (
            f'<p class="aw-rationale"><span class="aw-rationale-label">Why</span>'
            f'{_e(requirement.rationale)}</p>'
            if requirement.rationale
            else ""
        )
        parts.append(
            f'<div class="aw-requirement aw-requirement-{tone}" id="{_e(identifier)}">'
            f'<span class="aw-id">{_e(identifier)}</span>'
            f'<a class="aw-anchor-copy" href="#{_e(identifier)}" '
            f'aria-label="Link to {_e(identifier)}" title="Link to #{_e(identifier)}">#</a> {party}'
            f'<span class="aw-position">Requirement {index} of {total}</span>'
            f'<p><span class="aw-modal aw-modal-{tone}">{_e(requirement.modal)}</span> '
            f"{_e(requirement.statement)}</p>{rationale}</div>"
        )
    return "".join(parts)


# The one spelling of the rigor metadata name. Stated once so the renderer and anything reading a
# document back cannot drift apart on it.
RIGOR_META = "aw-spec-rigor"

# Values are SPEC_RIGORS in hub/hub/db/models.py ("sketch", "contract", "gate"). "sketch" is the
# default and blocks nothing, so it stays the plain neutral chip — only the two rigor levels that
# mean something (a stated intent, a refusal) get a tone, mirroring the modal treatment above:
# `gate` is the strongest (it can block a task's approval) and takes the accent; `contract` takes
# the warn tone. Any value not in this mapping (should not occur; spec_rigor.set_rigor validates
# on the way in) renders as the plain neutral chip rather than raising here.
_RIGOR_TONE = {"gate": "gate", "contract": "contract"}

# Values are the phases in hub/hub/spec_lifecycle.py. A phase not in this mapping renders as the
# plain neutral chip rather than raising, the same way an unknown rigor does.
_PHASE_TONE = {
    "approved": "done",
    "current": "done",
    "proposed": "waiting",
    "exploring": "quiet",
    "archived": "archived",
}


def _summary(payload: SpecPayload) -> str:
    """Counts, in the modal scheme, above the fold.

    Only what the payload itself knows. Coverage — whether a requirement has work linked — is the
    Hub's, not the renderer's, and claiming it here would state something this function cannot see.
    """
    if not payload.requirements:
        return ""

    by_tone: Dict[str, int] = {}
    for requirement in payload.requirements:
        tone = _MODAL_TONE.get(requirement.modal, "may")
        by_tone[tone] = by_tone.get(tone, 0) + 1

    parts: List[str] = []
    for tone, label in (("must", "MUST"), ("should", "SHOULD"), ("may", "MAY")):
        count = by_tone.get(tone, 0)
        if count:
            parts.append(
                f'<span class="aw-modal aw-modal-{tone}"><span class="aw-count">{count}</span> '
                f"{label}</span>"
            )

    tail = [f'<span class="aw-count">{len(payload.requirements)}</span> requirements']
    if payload.acceptance_criteria:
        tail.append(f'<span class="aw-count">{len(payload.acceptance_criteria)}</span> criteria')
    if payload.tasks:
        tail.append(f'<span class="aw-count">{len(payload.tasks)}</span> tasks')
    unresolved = sum(1 for question in payload.open_questions if not question.resolved)
    if unresolved:
        tail.append(
            f'<span class="aw-limits"><span class="aw-count">{unresolved}</span> '
            f'open question{"s" if unresolved != 1 else ""}</span>'
        )

    sep = '<span class="aw-summary-sep">·</span>'
    return f'<p class="aw-summary">{sep.join(parts + tail)}</p>'


def requirement_anchor(identifier: str) -> str:
    """Where a requirement sits in the rendered document.

    One definition, called by the renderer and by the requirement index, so an
    anchor recorded in the index cannot come to name a fragment the document
    does not contain.
    """
    return f"#{identifier}" if identifier else ""


def _link(identifier: str) -> str:
    return f'<a href="{_e(requirement_anchor(identifier))}">{_e(identifier)}</a>'


def _acceptance(payload: SpecPayload, identifiers: Dict[str, str]) -> str:
    if not payload.acceptance_criteria:
        return ""
    # Grouped by the requirement each criterion belongs to, in requirement
    # order. Submission order is the author's and is not this order: the first
    # agent-authored document listed FR-8, FR-8, FR-7, and a reader scanning the
    # table by requirement lost their place. The sort is stable, so criteria for
    # one requirement keep the order they were written in — that order carries
    # the author's emphasis and is theirs to choose.
    position = {requirement.key: index for index, requirement in enumerate(payload.requirements)}
    ordered = sorted(
        payload.acceptance_criteria,
        key=lambda criterion: position.get(criterion.requirement, len(position)),
    )
    rows = [
        '<table><colgroup><col style="width:13%"><col style="width:12%">'
        '<col style="width:32%"><col style="width:43%"></colgroup>'
        "<thead><tr><th>Requirement</th><th>Given</th><th>When</th><th>Then</th>"
        "</tr></thead><tbody>"
    ]
    previous_requirement: Optional[str] = None
    for criterion in ordered:
        identifier = identifiers.get(criterion.requirement, criterion.requirement)
        first = criterion.requirement != previous_requirement
        previous_requirement = criterion.requirement
        given = _e(criterion.given) if criterion.given else '<span aria-label="Not specified">—</span>'
        given_class = ' class="aw-cell-empty"' if not criterion.given else ""
        rows.append(
            f'<tr data-first="{"true" if first else "false"}"><td>{_link(identifier)}</td>'
            f"<td{given_class}>{given}</td>"
            f"<td>{_e(criterion.when)}</td><td>{_e(criterion.then)}</td></tr>"
        )
    rows.append("</tbody></table>")
    return "".join(rows)


def _tasks(payload: SpecPayload, identifiers: Dict[str, str]) -> str:
    if not payload.tasks:
        return ""
    items: List[str] = []
    for task in payload.tasks:
        refs = ", ".join(_link(identifiers.get(key, key)) for key in task.requirements)
        satisfies = f'<span class="aw-refs"><span>satisfies</span> {refs}</span>' if refs else ""
        # The title is what a board will show, so a reader of the document should see the same name
        # they will later see on the board. Without one the description carries the item, as before.
        if task.title.strip():
            body = f"<strong>{_e(task.title.strip())}</strong> — {_e(task.description)}"
        else:
            body = _e(task.description)
        items.append(f'<li class="aw-task">{body}{satisfies}</li>')
    return '<ul class="aw-task-list">' + "".join(items) + "</ul>"


def _algorithms(payload: SpecPayload) -> str:
    if not payload.algorithms:
        return ""
    parts: List[str] = []
    for algorithm in payload.algorithms:
        steps = "".join(f"<li>{_e(step)}</li>" for step in algorithm.steps)
        parts.append(f"<h3>{_e(algorithm.name)}</h3><ol>{steps}</ol>")
    return "".join(parts)


def _open_questions(payload: SpecPayload) -> str:
    # An absent section left a reader unable to tell a document whose questions
    # were asked and answered from one where none were ever asked — which is the
    # difference between a document that has been through an interview and one
    # that has not. Saying so costs a line.
    if not payload.open_questions:
        return '<p class="aw-empty">None outstanding.</p>'
    items = []
    for question in payload.open_questions:
        state = "resolved" if question.resolved else "open"
        chip = "aw-chip" if question.resolved else "aw-chip aw-chip-open"
        items.append(f'<li><span class="{chip}">{state}</span>{_e(question.question)}</li>')
    return "<ul>" + "".join(items) + "</ul>"


def _evidence(payload: SpecPayload) -> str:
    checked = _list(payload.evidence.checked)
    limits = _list(payload.evidence.limits)
    if not checked and not limits:
        return ""
    body = ""
    if checked:
        body += f"<h3>Checked</h3>{checked}"
    if limits:
        body += f'<h3 class="aw-limits">Limits</h3>{limits}'
    return body


# The corpus context a document is rendered with: where home is, what this document's parent is
# (if any), and this document's own children. Plain data — a `Manifest` read from `spec/index.json`
# plus each child's own summary, assembled by the caller (`spec_documents.build_corpus_context`).
# `spec_render.py` reaches neither the database nor the filesystem to produce it, and does not gain
# either capability by accepting it: everything here is already resolved.
@dataclass(frozen=True)
class CorpusChild:
    path: str
    title: str
    kind: str
    phase: str
    summary: str
    # Empty for every child except when this CorpusChild is itself part of the home document's
    # context (§3.6, decision D-S2-recursive: recursive on the home, direct children elsewhere).
    # `spec_documents.build_corpus_context` is what decides whether to populate this; a bare
    # `CorpusChild` with no descendants means exactly what it says elsewhere in the corpus.
    children: Tuple["CorpusChild", ...] = ()


@dataclass(frozen=True)
class CorpusContext:
    path: str  # this document's own corpus path — links are computed relative to it (§2.3)
    home: str
    parent: Optional[Tuple[str, str]]  # (path, title), or None where there is none
    children: Tuple[CorpusChild, ...]


def _relative_link(own_path: str, target_path: str) -> str:
    """A link from `own_path` to `target_path` that resolves on disk, with no Hub serving it.

    Both are corpus-relative paths like `spec/capabilities/x/spec.html`, not filesystem paths on
    whatever OS renders them — `posixpath` is used unconditionally so the output is always
    `/`-separated, per design D1/§2.3's example: `spec/capabilities/x/spec.html` reaching
    `spec/agentweave.html` is `../../agentweave.html`.
    """
    return posixpath.relpath(target_path, start=posixpath.dirname(own_path) or ".")


def _navigation(corpus: Optional[CorpusContext]) -> str:
    """Home and parent links, below the meta chips (decision D-S2-navstrip).

    Home is suppressed on the home document itself (§2.1) — there is nothing to link to that
    is not the page already open. Parent is rendered only where the manifest records one (§2.2).
    Absent `corpus`, this renders nothing, which is what keeps every caller that omits it (today,
    every caller) byte-identical to before this parameter existed (§1.3).
    """
    if corpus is None:
        return ""
    parts: List[str] = []
    if corpus.path != corpus.home:
        parts.append(f'<a href="{_e(_relative_link(corpus.path, corpus.home))}">Home</a>')
    if corpus.parent is not None:
        parent_path, parent_title = corpus.parent
        href = _e(_relative_link(corpus.path, parent_path))
        parts.append(f'<a href="{href}">{_e(parent_title)}</a>')
    if not parts:
        return ""
    return f'<p class="aw-nav">{"".join(parts)}</p>\n'


# design D8: two of today's thirty-five documents still carry the placeholder text a syncing
# change leaves behind, indistinguishable from a deliberately short real summary unless named.
# Either one, or a genuinely empty summary, renders as "no summary yet" rather than a blank cell.
_PLACEHOLDER_SUMMARY_PREFIX = "TBD - created by syncing change"


def _has_summary(summary: str) -> bool:
    return bool(summary) and not summary.startswith(_PLACEHOLDER_SUMMARY_PREFIX)


def _map_child(own_path: str, child: CorpusChild) -> str:
    phase_tone = _PHASE_TONE.get(child.phase, "")
    phase_chip_class = f"aw-chip aw-chip-phase-{phase_tone}" if phase_tone else "aw-chip"
    href = _e(_relative_link(own_path, child.path))
    summary = (
        f"<p>{_e(child.summary)}</p>"
        if _has_summary(child.summary)
        else '<p class="aw-empty">no summary yet</p>'
    )
    nested = (
        f'<ul class="aw-map-list">'
        f'{"".join(_map_child(own_path, grandchild) for grandchild in child.children)}'
        f"</ul>"
        if child.children
        else ""
    )
    return (
        '<li class="aw-map-item">'
        f'<a href="{href}">{_e(child.title)}</a> '
        f'<span class="aw-chip">{_e(child.kind)}</span>'
        f'<span class="{phase_chip_class}">{_e(child.phase)}</span>'
        f"{summary}{nested}"
        "</li>"
    )


def _map(corpus: Optional[CorpusContext]) -> str:
    """The generated map (§3): every child of the document being rendered, one level unless
    `corpus.children` itself carries further descendants — which only the home document's context
    does (decision D-S2-recursive, applied in `spec_documents.build_corpus_context`, not here; this
    function only walks whatever tree it is handed). Renders nothing where there are no children
    (§3.1), so a document with none is unaffected by this function existing.
    """
    if corpus is None or not corpus.children:
        return ""
    items = "".join(_map_child(corpus.path, child) for child in corpus.children)
    return (
        '<section class="aw-map">'
        '<h2 id="map">Map <span class="aw-note">'
        "(generated on reindex — hand edits here are overwritten)</span></h2>"
        f'<ul class="aw-map-list">{items}</ul>'
        "</section>"
    )


def render_document(
    payload: SpecPayload,
    identifiers: Dict[str, str],
    *,
    phase: str,
    stored_payload: Dict[str, Any],
    rigor: str = "sketch",
    corpus: Optional[CorpusContext] = None,
) -> str:
    """A self-contained document: inline style only, no external resource.

    `stored_payload` is embedded verbatim so a read of this file recovers
    everything that was submitted, including fields this schema version does not
    define.

    `rigor` is stated in the head and shown beside the phase, so anyone opening
    the file can see what happens to work that ignores it. Like the phase, the
    copy in the file is for whoever reads it and the database row is the
    authority — a gate whose value lives where the gated party can write it is
    not a gate.

    `corpus` is optional. Omitted (still true of every caller until corpus-aware-documents §4
    wires reindex up), the document is byte-identical to before this parameter existed (§1.3).
    Supplied, it adds two regions: navigation below the meta chips — a home link (suppressed on
    the home document itself) and a parent link (present only where the manifest records one),
    §2 — and, below the authored content, a generated map of the document's own children where it
    has any (§3), labelled as generated since a reindex overwrites it.
    """
    scope_body = ""
    if payload.scope.in_scope:
        scope_body += f"<h3>In scope</h3>{_list(payload.scope.in_scope)}"
    if payload.scope.non_goals:
        scope_body += f"<h3>Non-goals</h3>{_list(payload.scope.non_goals)}"
    elif payload.scope.in_scope:
        scope_body += (
            '<h3>Non-goals</h3><p class="aw-empty">None stated. Omission is not a ' "non-goal.</p>"
        )

    sections = "".join(
        [
            _section("Summary", "summary", _paragraphs(payload.summary)),
            _section("Problem", "problem", _paragraphs(payload.problem)),
            _section("Scope", "scope", scope_body),
            _section("Requirements", "requirements", _requirements(payload, identifiers)),
            _section("Acceptance criteria", "acceptance", _acceptance(payload, identifiers)),
            _section("Behaviour", "behaviour", _algorithms(payload)),
            _section("Design", "design", _paragraphs(payload.design)),
            _section("Evidence and coverage limits", "evidence", _evidence(payload)),
            _section("Lifecycle", "lifecycle", _paragraphs(payload.lifecycle)),
            _section("Tasks", "tasks", _tasks(payload, identifiers)),
            _section("Open questions", "open-questions", _open_questions(payload)),
        ]
    )

    rigor_tone = _RIGOR_TONE.get(rigor, "")
    rigor_chip_class = f"aw-chip aw-chip-rigor-{rigor_tone}" if rigor_tone else "aw-chip"
    phase_tone = _PHASE_TONE.get(phase, "")
    phase_chip_class = f"aw-chip aw-chip-phase-{phase_tone}" if phase_tone else "aw-chip"

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_e(payload.title)}</title>\n"
        f'<meta name="aw-spec-kind" content="{_e(payload.kind)}">\n'
        f'<meta name="aw-spec-status" content="{_e(phase)}">\n'
        f'<meta name="{RIGOR_META}" content="{_e(rigor)}">\n'
        f'<meta name="aw-spec-schema-version" content="{_e(payload.schema_version)}">\n'
        f"<style>\n{_STYLE}\n</style>\n"
        "</head>\n<body>\n"
        f"<h1>{_e(payload.title)}</h1>\n"
        f'<p class="aw-meta"><span class="aw-chip">{_e(payload.kind)}</span>'
        f'<span class="{phase_chip_class}">{_e(phase)}</span>'
        f'<span class="{rigor_chip_class}">{_e(rigor)}</span></p>\n'
        f"{_navigation(corpus)}"
        f"{_summary(payload)}\n"
        f"{sections}\n"
        f"{_map(corpus)}"
        f"{embed_payload(stored_payload)}\n"
        "</body>\n</html>\n"
    )
