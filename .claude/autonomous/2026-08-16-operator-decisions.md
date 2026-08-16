# Operator decisions — 2026-08-16 review session

The operator worked through the judgement backlog. Every decision below records the **rejected
alternative and its reason**, so a later session that sees only the outcome does not re-propose what
was already turned down.

Open judgement tasks at the start of this session: **52** across 13 changes (excluding the
`hub-native-experience` umbrella). At the end: **31**.

---

## Ticked

| task | change | decision |
|---|---|---|
| 9.1 | a-document-earns-its-name | Placeholder (`ivory-salamander`) is **pleasant, keep it**. Visible 71s. |
| 8.5 | a-requirement-knows-its-work | **Nobody holds `can_accept_evidence` by default**; the operator grants it. |
| 5.3 | a-gate-that-only-evidence-opens | **Keep `contract`, give it a consequence.** Work filed as new 5.5. |
| 5.4 | a-gate-that-only-evidence-opens | **Default stays loose, but never silent.** |
| 6.5 | the-spec-tool-reaches-the-agent | **A turn with no `conversation_id` keeps opening a new conversation.** |
| 5.2, 5.5 | run-without-a-git-repository | Accepted the loop's live findings. |
| 4.1, 4.2, 4.3 | a-posture-that-survives-the-handoff | Accepted the loop's live findings. |
| 5.1, 5.2, 5.3, 5.4 | the-interview-is-a-conversation | Accepted the loop's live findings. |
| 5.1 | the-tool-list-matches-the-tools | Accepted: `submit_spec_document` observed, first time ever. |

The last ten were accepted **on evidence, after reading all ten** — each carries a run id, its
tool-call order and its cost in `2026-08-15-judgement-evidence.md`. Two were stronger than a plain
answer: `4.2` found the **task's own wording described the wrong test** (it asked for cross-agent
propagation; the spec requires same-agent continuity) and corrected it, and `5.2` caught the agent
stating its own stop explicitly rather than answering its own questions.

## Structural decisions

### d2 — the `hub-native-experience` umbrella: **split out the real work, then archive**

119 done / 69 open, and it has distorted every count for two weeks. Accepted the loop's
code-verified proposal in `2026-08-15-triage.md`:

- **Sections 9–12 are dead weight** — closed by five already-archived successor changes.
- **Genuinely undelivered:** 13.4, 13.9, 13.11, part of 13.3, **all of section 15**, plus section
  14's `14.11`/`14.12` (no successor built an in-place proposal/authoring mechanic) and `14.14`
  (scope discipline is charter prose, never an enforced control), with small remainders of `14.5`
  and `14.13`.
- **Action:** carry only that into one or two new focused changes, then archive the umbrella.

**Rejected:** archiving wholesale — `14.11`/`14.12`/`14.14` are real gaps that would silently vanish
from the record and only resurface when they bite. **Also rejected:** leaving it open, which keeps
the single biggest distortion on the board.

### d4 — `.claude/handoffs/` **stays tracked**

Carried unanswered since handoff 0044. The chain is load-bearing: `/resume` reads it, and this
week's run reconstructed its whole context from handoff 0047. **Rejected** untracking either the
handoffs or `.claude/autonomous/`: a fresh clone or a second machine would lose the reasoning chain
entirely, and the unattended run depended on exactly that chain surviving. The cost — repo growth
every session — is accepted knowingly.

### Bucket C — two mis-filed tasks go to the next loop

`answers-arrive-together` **1.4** ("reproduce the defect against the running Hub") and **4.6** ("two
answers completing a batch concurrently produce one entry, not two") are filed under human
verification but are **agent-verifiable**: a live reproduction and a concurrency test. The next loop
should execute them as tests. Closes 2 of that change's 7 open items with no operator involvement.

---

## Parked — needs the operator's own hands on the app

The operator's instruction: *"Park them all, judge after I drive it tomorrow."* These need
first-hand use, not a reconstruction — a lesson learned this session, when judging the spec document
from a summary proved weaker than looking at it.

**Do not have a loop answer these.** A loop may add evidence beneath them; it may not tick them.

| change | tasks |
|---|---|
| hub-owns-the-spec-document | 17.1, 17.2, 17.3, 17.4, 17.6, 17.8 |
| blocked-and-conversation-binding | 8.10, 8.11, 8.12, 8.13 |
| answers-arrive-together | 5.1, 5.2, 5.3, 5.4, 5.5 |
| a-document-earns-its-name | 9.2, 9.3, 9.4 |
| a-gate-that-only-evidence-opens | 5.1, 5.2 |
| a-requirement-knows-its-work | 8.1, 8.2, 8.4 |
| declining-a-question | 6.8, 6.9 |
| run-without-a-git-repository | 5.1, 5.3 |
| the-spec-tool-reaches-the-agent | 6.1, 6.4 |
| the-interview-is-a-conversation | 5.5 |
| a-posture-that-survives-the-handoff | 4.4 |
| the-tool-list-matches-the-tools | 5.2, 5.3 |

**Known already, before tomorrow:** `17.2`/`5.2`/`6.1` will not be a clean tick — the operator's
verdict was *"readable but uglier"*, with six specific reasons in
`2026-08-16-operator-ux-findings.md`. And `8.1` ("is the coverage state legible?") already has its
answer: **no** — a requirement whose evidence was rejected reads as `in_progress`.

## Not judgement calls at all

- **12.3** (`hub-owns-the-spec-document`) — deliberately not implemented; the task itself argues D9
  should be **amended**, because auto-binding the spec charter would make "no charter" unreachable
  and contradict the operator's *"I can skip it."* Needs an operator ruling on amending D9, not an
  implementation.
- **16.8** — partly covered; the missing assertion would be that absent code stays absent.
- **5.5** (`a-gate-that-only-evidence-opens`) — new work created by this session's 5.3 decision.

## Ready to archive with no further input

**`the-hubs-procedure-outranks-an-installed-one` — 25 done / 0 open.** Nothing blocks it.
