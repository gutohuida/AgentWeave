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

from html import escape
from typing import Any, Dict, List

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
  --aw-accent: #0969da; --aw-warn: #9a6700; --surface-2: #eaeef2; --surface: #f6f8fa;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --border: #30363d;
    --aw-accent: #4493f8; --aw-warn: #d29922; --surface-2: #21262d; --surface: #161b22;
  }
}
:root[data-theme="light"] {
  --bg: #ffffff; --fg: #1f2328; --muted: #656d76; --border: #d8dee4;
  --aw-accent: #0969da; --aw-warn: #9a6700; --surface-2: #eaeef2; --surface: #f6f8fa;
}
:root[data-theme="dark"] {
  --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --border: #30363d;
  --aw-accent: #4493f8; --aw-warn: #d29922; --surface-2: #21262d; --surface: #161b22;
}
* { box-sizing: border-box; }
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
.aw-chip { display: inline-block; padding: .1rem .5rem; border-radius: 999px;
           background: var(--surface-2); font-size: .78rem; margin-right: .4rem; }
.aw-requirement { border-left: 3px solid var(--border); padding: .1rem 0 .1rem .9rem;
                  margin: 1.1rem 0; }
.aw-requirement-must { border-left-color: var(--aw-accent); }
.aw-requirement-should { border-left-color: var(--aw-warn); }
.aw-requirement-may { border-left-color: var(--border); }
.aw-id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .8rem;
         color: var(--muted); }
.aw-modal { font-weight: 600; }
.aw-modal-must { color: var(--aw-accent); }
.aw-modal-should { color: var(--aw-warn); }
.aw-modal-may { color: var(--fg); font-weight: 400; }
.aw-chip-rigor-gate { color: var(--aw-accent); border: 1px solid var(--aw-accent); }
.aw-chip-rigor-contract { color: var(--aw-warn); border: 1px solid var(--aw-warn); }
.aw-rationale { color: var(--muted); font-size: .9rem; }
.aw-refs { font-size: .82rem; color: var(--muted); }
.aw-note { color: var(--muted); font-style: italic; }
.aw-empty { color: var(--muted); }
table { border-collapse: collapse; margin: .75rem 0; width: 100%; }
th, td { border: 1px solid var(--border); padding: .4rem .6rem; text-align: left;
         vertical-align: top; font-size: .92rem; }
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
    return f'<section><h2 id="{anchor}">{_e(title)}</h2>{body}</section>'


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
    for requirement in payload.requirements:
        identifier = identifiers.get(requirement.key, "")
        tone = _MODAL_TONE.get(requirement.modal, "may")
        party = f'<span class="aw-chip">{_e(requirement.party)}</span>' if requirement.party else ""
        rationale = (
            f'<p class="aw-rationale">{_e(requirement.rationale)}</p>'
            if requirement.rationale
            else ""
        )
        parts.append(
            f'<div class="aw-requirement aw-requirement-{tone}" id="{_e(identifier)}">'
            f'<span class="aw-id">{_e(identifier)}</span> {party}'
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
        "<table><thead><tr><th>Requirement</th><th>Given</th><th>When</th><th>Then</th>"
        "</tr></thead><tbody>"
    ]
    for criterion in ordered:
        identifier = identifiers.get(criterion.requirement, criterion.requirement)
        rows.append(
            f"<tr><td>{_link(identifier)}</td><td>{_e(criterion.given)}</td>"
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
        satisfies = f'<span class="aw-refs"> — satisfies {refs}</span>' if refs else ""
        # The title is what a board will show, so a reader of the document should see the same name
        # they will later see on the board. Without one the description carries the item, as before.
        if task.title.strip():
            body = f"<strong>{_e(task.title.strip())}</strong> — {_e(task.description)}"
        else:
            body = _e(task.description)
        items.append(f"<li>{body}{satisfies}</li>")
    return "<ul>" + "".join(items) + "</ul>"


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
        items.append(f'<li><span class="aw-chip">{state}</span>{_e(question.question)}</li>')
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
        body += f"<h3>Limits</h3>{limits}"
    return body


def render_document(
    payload: SpecPayload,
    identifiers: Dict[str, str],
    *,
    phase: str,
    stored_payload: Dict[str, Any],
    rigor: str = "sketch",
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
        f'<span class="aw-chip">{_e(phase)}</span>'
        f'<span class="{rigor_chip_class}">{_e(rigor)}</span></p>\n'
        f"{sections}\n"
        f"{embed_payload(stored_payload)}\n"
        "</body>\n</html>\n"
    )
