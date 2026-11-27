---
description: The project's knowledge vault — transcripts, rules, decisions and documents your agents read, with facts that cite their sources.
---

# Knowledge vault

!!! info "New"
    The vault is one of AgentWeave's newest areas. It works end to end, but expect it to grow.

Agents only know what you tell them and what is in the code. Much of what matters lives elsewhere:
what was said in a meeting, the rules that always hold, decisions already made, a PDF from a
customer. The **vault** is where that goes. Every agent turn is told the vault exists and how much
it holds, and agents read what their work needs.

<figure class="aw-shot" markdown>
![The Vault tab: a meeting transcript and a rules document, with the transcript open by speaker](../assets/screenshots/vault-light.webp#only-light)
![The Vault tab: a meeting transcript and a rules document, with the transcript open by speaker](../assets/screenshots/vault-dark.webp#only-dark)
</figure>

## The Overview

The **Vault** tab opens on an **Overview** of what the vault holds. It states how many sources and
facts there are, how many sources of each kind, the open disagreements, the reports referred to you,
the sources with no fact drawn yet, and the private sources held on another machine. Each figure
equals what the matching view lists.

Under **Important facts**, three lists show facts worth a look, each with its count:

- **Contradicted a spec**: the newest spec vault check of a document found the fact in conflict with
  a requirement that still says what was judged, and the fact still stands.
- **Cited by a spec**: a requirement lists the fact among its facts.
- **Opened by agents**: agents have opened the source it comes from.

It also lists the five sources agents opened most (with how many times, when last, and which
agents), and the five added most recently. Seeing a fact in a turn's vault list does not count as
opening it. While the uses are being read, the Overview says so, and if that fails it says what
failed.

## Adding sources

Drop files or folders anywhere on the **Vault** tab, use **Add**, or paste text. Text, Markdown,
PDFs and images are accepted, up to 10 MiB each. For each source you choose:

- **Kind**: **Transcript** (a meeting or call, as it was said), **Rule** (something that must always
  hold), **Decision** (a choice made, and why), **Document** (reference material), **Note** or
  **Example**.
- **Storage**: **In the repository** (under `knowledge/sources/`, tracked with your code), or
  **Private, this machine** (kept under `~/.agentweave/hub/vaults/`, with only a stub in the
  project).
- **When it was said**: an optional date. When two sources disagree, the later one is presumed to
  hold.

From a terminal, `agentweave vault add` does the same. Agents can add files too, with `vault_add`.

```bash
agentweave vault add notes/finance-sync.md --type transcript --dated 2026-10-20 --distil
```

## Facts

With **vault distillation** turned on (**Project settings → Manager**), the Hub reads each new
source and writes down the **facts** it states. Each fact cites the exact lines it rests on, and
**Show in the source** highlights them. PDFs and images are transcribed first. **Extract facts**
(or **Extract again**) runs it on demand.

The **Facts** view in the Vault lists every fact in the map: facts that still stand first,
superseded ones last, each newest first. Each row shows the claim, its marks (*disputed*,
*superseded*, *source changed*) and its source. Opening a fact opens its source with the cited lines
marked.

The reader has three views: **Text**, **Facts**, and **Used by**, which shows which agents read
the source and how often.

## When sources disagree

Distillation also checks new facts against the ones already in the vault. A contradiction appears
under **Review → Disagreements**. You decide **This one holds** or **Neither holds**, with a
reason, and the decision is recorded.

An agent that finds a vault entry wrong reports it, with `vault_report`. With **vault reports**
turned on, the Hub looks into each report: it corrects the fact from its source, answers why the
fact stands, or refers it to you under **Review → Reports**.

## Searching

The Vault search matches the text you type, ignoring case; it does not match meaning. It lists
**Facts** whose claim contains the text (with the text marked), and **Documents** whose name,
opening or text contains it. A document whose text matches shows its first three matching lines
with line numbers, and how many more match. Archived sources, and the text of private sources held
on another machine, are not searched. Type at least two characters.

## Checking specifications against the vault

With the **spec vault check** turned on, each specification you check is read against the vault's
facts, and a requirement that contradicts one gets a warning on the specification's health line.
It is a warning, never a refusal. You decide.

In the same pass the check names, for each requirement, the facts that **possibly back** it. The full
specification page shows them beside the requirement, marked *possible, not confirmed*. They are
never final: they do not count as facts the requirement lists, and raise no warning. A requirement's
own `facts` field is what makes a fact cited. See
[Specification documents](../reference/spec-documents.md#requirements).

## Turning it on

Vault sources work with nothing turned on: agents can list and read them. The model-backed parts
are **manager jobs**, each off until you enable it and choose a runner and model under **Project
settings → Manager**:

| Manager job | Runs when | Does |
|---|---|---|
| **Vault distillation** | a source is added | Extracts facts with line citations, then checks them for contradictions. |
| **Vault reports** | an agent reports an entry | Corrects, answers, or refers the report to you. |
| **Spec vault check** | a specification is checked | Warns about requirements that contradict vault facts. |
| **Conversation titles** | a turn completes | Names a conversation after its first exchange. Threads started by flows, builds and the mender are titled when created, with no model call. |

While a manager job runs on the vault, a manager icon shows in the Vault header. See
[Manager work you can see](the-app.md#manager-work-you-can-see).

Manager jobs are background calls. They never make an agent look busy, their spend counts towards
the project's token budget, and each firing is listed in the Manager section's history.
