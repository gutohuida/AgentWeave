"""How many unrendered query errors are operator-visible failures? Measurement for `DECISIONS.md` R-1.

R-1's evidence table sizes F197 as *"133 `useQuery` declarations; 62 of 97 component files never
mention `error`"* and says in the same breath that this is an order-of-magnitude grep rather than a
defect count. This replaces it with a count. It changes no product code and reads no database.

    py -3.11 scripts/drive/n11_query_error_surface.py

The unit of measurement is a **call site**, not a declaration and not a file. A declaration cannot
be a defect on its own — three components calling one hook are three chances to render an error,
and one hook file that never mentions `error` is one missing chance, not three. The `62 of 97`
grep counts *files*, which is neither.

Two places the error can be lost, and the script separates them because they have different fixes:

1. **The hook discards it.** A hook that destructures `useQuery` internally and returns a narrower
   object with no `error`/`isError` field puts the error out of every caller's reach. No component
   grep can see this, and no component-level fix can repair it.
2. **The call site does not bind it.** The ordinary case, and the one the `62 of 97` grep was
   reaching for.

What the script decides mechanically, and what it hands back:

* Mechanical: the declarations, their options (`refetchInterval`, `enabled`, `retry`), whether the
  hook exposes `error`, every call site, whether the site binds `error`/`isError`, and whether the
  bound name is used again in the file (a bound-and-never-used `error` renders nothing).
* By hand: what each unhandled site *renders instead*. That cannot be derived from a grep, so every
  unhandled site is classified in `CLASSIFIED`, each entry naming the line it was read off — the
  same discipline as `n10_route_reachability.py`'s `HAND_RESOLVED`. An unclassified site is
  reported as `UNCLASSIFIED` rather than silently bucketed.

**The classification rule, written down before it was applied.**

A query error is *operator-visible* when a failed fetch changes what the operator sees on a surface
they opened **and what they see instead makes a claim that is false**. It is *correctly invisible*
when the failure leaves them nothing to act on wrongly. Per site:

* `MISREPORT` — the site substitutes a default (`data: x = []`, `?? 0`, `data?.field`) and renders
  it as fact: an empty list, a zero count, a "none" badge, or a skeleton with no terminal state.
  The operator cannot tell a failure from a truthful empty. This is F197's shape.
* `BLANK` — the region renders nothing, or a neutral placeholder that asserts nothing. A capability
  quietly disappears; no false sentence is put on the screen.
* `HANDLED` — `error`/`isError` is bound *and* used.

**Two labels the rule gained while it was being applied, recorded because the rule was supposed to
be fixed first.** Both were forced by sites the three labels could not describe honestly, and both
*narrow* `MISREPORT` rather than widen it, so neither inflates the headline count:

* `SUPPRESSED`, split out of `BLANK`. A pending-approval card that does not render says nothing
  false — but it is not a missing decoration either, and lumping the operator's blocked run in with
  a missing avatar colour would have hidden the more interesting half of `BLANK`.
* `NAMED`, which did not exist in the three-label rule at all. `RunnersPage.tsx:198` renders *"The
  model catalog is unavailable"* from `!!catalog`, binding no `error`. Under the original rule it
  was unhandled and blank; it is neither, and it is the counter-example any repo check has to
  survive.

**The poll pardon, and its limit.** A query with `refetchInterval` retries forever and React Query
keeps the last successful data, so a transient failure mid-poll really is invisible and correctly
so. That pardon requires a first success. A poll that fails from its first attempt — Hub down,
project unreadable, a 500 — renders the same false empty as any other query, so `POLL` is recorded
as a separate flag rather than as a class: it downgrades a steady-state failure, never a cold one.

**Known blind spot, the same one N-10 carried.** Call sites are found by symbol, one level deep, so
a site inside a component that nothing imports is counted as a live site. F260 is that shape
(`MessagesFeed` is imported by nothing and is absent from the shipped bundle). Every count here is
therefore an upper bound on live sites, and the MISREPORT count is an upper bound in the same way.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI_SRC = REPO / "hub" / "ui" / "src"
API_DIR = UI_SRC / "api"

# What each unhandled call site renders when `data` is absent, read off the lines named in the
# reason. Four labels, applied by the rule in the module docstring:
#
#   MISREPORT  a statement reaches the screen — words, a number, a badge, or a control rendered
#              with no options — that the operator reads as true and that is not.
#   SUPPRESSED an alert, a warning or an affordance the operator was waiting for does not render
#              at all. Nothing false is said; something true is not said.
#   BLANK      a decoration, a label or a lookup is missing. Nothing is lost that carries a claim.
#   NAMED      the site says the data is unavailable, without ever binding `error`. Not a defect —
#              and the reason a check that merely asserts `error` is bound would misfire here.
#
# `PICKER` marks the MISREPORT sites whose false statement is an empty `<select>` or option list,
# so the count can be read with them and without them.
# One row per site, one line each: black would make this table 500 lines.
# fmt: off
CLASSIFIED: list[tuple[str, int, str, str, str]] = [
    # (path under hub/ui/src, line, class, flag, what it renders instead)
    ('App.tsx', 92, 'MISREPORT', '', '`projects ?? []` reaches ProjectManagerModal (:598) and the current-project lookup (:234): an operator with projects is shown none'),
    ('App.tsx', 93, 'MISREPORT', '', '`agents = []` is handed to the sidebar (:631) — the roster reads as empty'),
    ('App.tsx', 161, 'MISREPORT', '', "both behaviours at one site: `conversationsKnown` (:300) correctly treats undefined as 'not known yet', and `conversations={…?? []}` (:632) hands the tree an empty list"),
    ('App.tsx', 164, 'MISREPORT', '', '`documents={specDocuments?.documents ?? []}` (:633)'),
    ('App.tsx', 165, 'MISREPORT', '', '`tasks={allTasks ?? []}` (:634)'),
    ('components/accounting/AccountingPanel.tsx', 15, 'BLANK', '', '`if (!data) return null` (:16)'),
    ('components/accounting/AccountingPanel.tsx', 22, 'MISREPORT', '', "`if (isLoading || !data)` returns the Budgets skeleton (:34-42); `isLoading` is false after an error, so the skeleton is terminal — F197's shape exactly"),
    ('components/activity/ActivityLog.tsx', 61, 'BLANK', '', 'agents only build a colour map (:62)'),
    ('components/agents/AgentActivityTab.tsx', 23, 'MISREPORT', '', "the merged feed renders 'No activity yet' (:112); this hook also hides its own error from every caller"),
    ('components/agents/AgentActivityTab.tsx', 24, 'MISREPORT', '', 'same feed, same sentence (:112)'),
    ('components/agents/AgentCreateDialog.tsx', 149, 'MISREPORT', 'PICKER', '`providers = catalog?.providers ?? []` (:168) — the create dialog offers no provider'),
    ('components/agents/AgentCreateDialog.tsx', 150, 'SUPPRESSED', '', '`launchability?.[…]` (:84, :171) only decides whether a warning verdict is shown'),
    ('components/agents/AgentCreateDialog.tsx', 151, 'MISREPORT', 'PICKER', '`charters.map` into `<option>` (:231)'),
    ('components/agents/AgentOutputPanel.tsx', 152, 'BLANK', '', 'only `isLoading` is taken and `lines` is deliberately unread (:148-152)'),
    ('components/agents/AgentOutputPanel.tsx', 197, 'SUPPRESSED', '', '`permissionRequests = []` (:1127): a run waiting on an approval renders no card'),
    ('components/agents/AgentOutputPanel.tsx', 198, 'SUPPRESSED', '', '`pendingQuestion` null (:206) and `questions={[]}` (:1129): a run waiting on an answer renders no ask'),
    ('components/agents/AgentOutputPanel.tsx', 207, 'MISREPORT', '', '`conversations = []` drives the list and `currentConversation` (:317)'),
    ('components/agents/AgentOutputPanel.tsx', 319, 'MISREPORT', '', "`roster = []` (:1032) and the agent's own row missing (:321)"),
    ('components/agents/AgentOutputPanel.tsx', 320, 'BLANK', '', '`runners` only resolves a label (:322)'),
    ('components/agents/AgentOutputPanel.tsx', 330, 'MISREPORT', '', '`timelineEvents = []` (:1033)'),
    ('components/agents/AgentOutputPanel.tsx', 331, 'BLANK', '', '`recentTurns={accounting?.recent_turns}` (:1040) — the figure is absent'),
    ('components/agents/AgentOutputPanel.tsx', 332, 'BLANK', '', '`{conversationUsage && …}` (:961)'),
    ('components/agents/AgentOutputPanel.tsx', 333, 'SUPPRESSED', '', '`queueStatus` undefined — the waiting indicator does not render'),
    ('components/agents/AgentOutputPanel.tsx', 337, 'SUPPRESSED', '', '`hasQueuedWork` false (:343): queued work reads as none'),
    ('components/agents/AgentOutputPanel.tsx', 346, 'MISREPORT', 'PICKER', '`workspacePaths={[]}` (:1152)'),
    ('components/agents/AgentOutputPanel.tsx', 347, 'MISREPORT', '', '`timelineEntries = chat.data?.entries ?? []` (:350) — the transcript reads as empty'),
    ('components/agents/AgentOutputPanel.tsx', 348, 'MISREPORT', '', 'the same `chat` (:349-350) when no conversation is selected'),
    ('components/agents/AgentOutputPanel.tsx', 489, 'SUPPRESSED', '', '`offeredCheckpoint` undefined (:490) — the checkpoint offer does not render'),
    ('components/agents/AgentSettingsControls.tsx', 178, 'MISREPORT', 'PICKER', '`permissionModeValues(catalog)` (:180) yields no options'),
    ('components/agents/AgentSettingsControls.tsx', 220, 'MISREPORT', 'PICKER', "'Loading runners…' is shown while `isLoading` (:224) and an empty select after the error (:242)"),
    ('components/agents/AgentSettingsControls.tsx', 259, 'MISREPORT', 'PICKER', 'same shape for charters (:263, :282)'),
    ('components/agents/AgentSettingsPage.tsx', 42, 'MISREPORT', '', "`roster.find` (:43) fails and the page renders 'This agent is no longer in the roster.' (:55)"),
    ('components/agents/AgentSettingsPage.tsx', 444, 'MISREPORT', '', "'No sessions yet.' (:451)"),
    ('components/agents/ComposerModelControls.tsx', 176, 'SUPPRESSED', '', 'the model controls do not render; the file states this intent for an undeclared provider (:167)'),
    ('components/agents/ConversationView.tsx', 107, 'MISREPORT', '', '`buildInventory(specList)` is empty (:119) and `specList={specList}` (:387) — the spec surface reads as having nothing in it'),
    ('components/agents/ConversationView.tsx', 112, 'BLANK', '', 'title lookup `?? null` (:114)'),
    ('components/agents/ConversationView.tsx', 280, 'MISREPORT', 'PICKER', '`paths={workspacePaths}` (:344)'),
    ('components/agents/ConversationView.tsx', 287, 'MISREPORT', '', '`runningLoopCount(allLoops)` renders a 0 count on the Loops tab (:299)'),
    ('components/agents/NewConversationSurface.tsx', 53, 'MISREPORT', '', '`roster.map` (:171) is the agent list this surface exists to show'),
    ('components/agents/NewConversationSurface.tsx', 54, 'BLANK', '', 'runner label lookup (:60)'),
    ('components/agents/NewConversationSurface.tsx', 55, 'MISREPORT', 'PICKER', '`workspacePaths={…}` (:209)'),
    ('components/charters/ChartersPage.tsx', 29, 'MISREPORT', '', "`charters.length === 0` renders EmptyState 'No charters yet' (:90-93)"),
    ('components/environment/DiagnosticsPanel.tsx', 8, 'MISREPORT', '', '`JSON.stringify(data ?? {}, null, 2)` (:10) renders `{}` as the diagnostics'),
    ('components/environment/ProjectSettingsPanel.tsx', 49, 'BLANK', '', '`projects.find` only names the project (:50)'),
    ('components/environment/ProjectSettingsPanel.tsx', 53, 'MISREPORT', '', '`if (!settings) return` (:67) leaves `form` unset, so the skeleton at :78 is terminal — this site *is* F197'),
    ('components/environment/ProjectSettingsPanel.tsx', 54, 'BLANK', '', "placeholder 'Not chosen' (:191); the suggestion button simply does not appear"),
    ('components/environment/ProjectSettingsPanel.tsx', 55, 'MISREPORT', 'PICKER', 'runner selects (:170, :278)'),
    ('components/environment/ProjectSettingsPanel.tsx', 56, 'BLANK', '', '`catalog?.providers` optional at both uses (:91, :292)'),
    ('components/instructions/InstructionsPage.tsx', 9, 'MISREPORT', '', "`if (data) setContent(data.content)` (:15-16) never fires, so the editor renders empty with Save enabled (:38-40) — a save then writes '' over the stored instructions"),
    ('components/jobs/JobCard.tsx', 251, 'SUPPRESSED', '', '`canOpenQueue` false (:256) hides the open-queue button'),
    ('components/jobs/JobCard.tsx', 358, 'MISREPORT', '', "RunHistory renders 'No runs yet' (:152-154) although its own comment (:146-147) says that claim must not be made before the answer arrives — the guard it added is `isLoading`, which is false on error"),
    ('components/jobs/JobForm.tsx', 32, 'MISREPORT', 'PICKER', '`agents?.map` into `<option>` (:168)'),
    ('components/jobs/JobsPage.tsx', 34, 'MISREPORT', '', "EmptyState 'No jobs yet — Create scheduled jobs to automatically trigger agents' (:133-138) and the totals row (:176-178)"),
    ('components/layout/AgentTree.tsx', 52, 'MISREPORT', '', "the tree's conversations (:62) and `archivedCount ?? 0` (:98)"),
    ('components/layout/AgentTree.tsx', 58, 'MISREPORT', '', "`archived.data?.conversations ?? []` (:72) behind the reason 'Nothing archived yet' (:116)"),
    ('components/layout/RecencyView.tsx', 46, 'MISREPORT', '', '`open.data?.conversations ?? []` (:55) and `archivedCount ?? 0` (:56)'),
    ('components/layout/RecencyView.tsx', 48, 'MISREPORT', '', "`archived.data?.conversations ?? []` (:57) behind 'Show archived (0)' (:150)"),
    ('components/layout/Sidebar.tsx', 157, 'MISREPORT', '', "`projects.map` (:364, :504) is the sidebar's project list"),
    ('components/layout/StatusBar.tsx', 15, 'MISREPORT', '', 'every count falls back to zero (:25-28): 0 pending messages, 0 active tasks, 0 unanswered questions, 0 agents'),
    ('components/layout/StatusBar.tsx', 16, 'SUPPRESSED', '', '`contextWarningCount` (:21) drops to 0 and the context warning (:113) does not render'),
    ('components/layout/StatusBar.tsx', 19, 'SUPPRESSED', '', '`exhausted={accounting?.budget.exhausted ?? false}` (:122) — an exhausted budget renders no notice'),
    ('components/logs/LogsView.tsx', 123, 'MISREPORT', '', "'No log entries yet. Trigger some activity to see entries here.' (:362)"),
    ('components/logs/LogsView.tsx', 128, 'MISREPORT', 'PICKER', "the agent filter's options (:251)"),
    ('components/messages/MessagesFeed.tsx', 20, 'MISREPORT', 'DEAD', "EmptyState 'No messages' (:143-145) — in a component nothing imports (F260), so no operator reaches it"),
    ('components/messages/MessagesFeed.tsx', 21, 'MISREPORT', 'DEAD', "EmptyState 'No message history' (:143-145), same dead component"),
    ('components/messages/MessagesFeed.tsx', 26, 'MISREPORT', 'DEAD', 'the agent filter built from `allMessages` (:27), same dead component'),
    ('components/overview/OverviewBudgetSummary.tsx', 11, 'MISREPORT', '', '`if (isLoading || !data)` returns a skeleton (:13) that is terminal after an error'),
    ('components/overview/OverviewPage.tsx', 79, 'MISREPORT', '', "'No agents connected — Run `agentweave start` to connect agents.' (:145-147), which also tells the operator to do the wrong thing"),
    ('components/overview/OverviewPage.tsx', 80, 'SUPPRESSED', '', '`unanswered = questions.length` is 0 (:84) so the QuestionInterruptCard does not render (:130)'),
    ('components/overview/OverviewPage.tsx', 81, 'MISREPORT', '', '`{taskCount} task` in the page header (:117) and the per-status counts (:86-91)'),
    ('components/overview/OverviewPage.tsx', 82, 'BLANK', '', '`status?.project_name` is conditional (:118)'),
    ('components/projects/DirectoryPicker.tsx', 28, 'MISREPORT', '', '\'No subdirectories\' (:162-163) — while the branch immediately above it renders the server\'s *stated* refusal, "Can\'t read this directory: {reason}" (:158-161)'),
    ('components/projects/DirectoryPicker.tsx', 29, 'MISREPORT', 'PICKER', '`roots = rootsData?.roots ?? []` (:47) leaves the roots strip empty'),
    ('components/projects/ProjectManagerModal.tsx', 33, 'BLANK', '', '`nativeAvailability?.available` (:141, :169) falls back to the manual path — deliberate degradation'),
    ('components/quality/QualityHealthPanel.tsx', 25, 'MISREPORT', '', "EmptyState 'No quality governance configured' (:43-52) — a claim about the project's governance, made from a failed fetch"),
    ('components/quality/QualityHealthPanel.tsx', 26, 'MISREPORT', '', "`(tasks ?? [])` filters render 'All reviewed tasks clear' (:103)"),
    ('components/questions/QuestionsPanel.tsx', 87, 'BLANK', '', '`{answered && answered.length > 0 && …}` (:197) hides a history disclosure'),
    ('components/questions/QuestionsPanel.tsx', 91, 'BLANK', '', 'the per-agent timeout lookup (:143)'),
    ('components/runners/RunnersPage.tsx', 22, 'MISREPORT', '', "`{!runners || runners.length === 0}` renders EmptyState 'No runners yet' (:81-84)"),
    ('components/runners/RunnersPage.tsx', 198, 'NAMED', '', "`catalogAvailable = !!catalog` (:202) renders 'The model catalog is unavailable — this runner will use the provider's default.' (:292). No `error` is bound and none is needed"),
    ('components/spec/SpecCoverageBar.tsx', 84, 'BLANK', '', '`if (!data …) return null` (:87)'),
    ('components/spec/SpecDocumentPanel.tsx', 69, 'MISREPORT', '', 'the `specDoc ? … : ` else branch is a second skeleton (:329-334), terminal after an error'),
    ('components/spec/SpecDocumentTasksLink.tsx', 20, 'BLANK', '', '`if (!document …) return null` (:24)'),
    ('components/spec/SpecDocumentTasksLink.tsx', 22, 'BLANK', '', 'same guard (:24)'),
    ('components/spec/SpecPage.tsx', 35, 'MISREPORT', '', "EmptyState 'Everything here is archived' (:98-107) — a failed spec-list fetch tells the operator their documents are archived"),
    ('components/spec/SpecPhaseBar.tsx', 23, 'SUPPRESSED', '', '`if (!document) return null` (:33) removes the phase controls and the rigor refusal with it'),
    ('components/spec/SpecProposalsPanel.tsx', 22, 'SUPPRESSED', '', '`if (proposals.length === 0) return null` (:30) — pending edit proposals waiting on the operator do not render'),
    ('components/spec/SpecRailNav.tsx', 30, 'MISREPORT', '', "`buildInventory(specList)` (:31) leaves the rail's document list empty"),
    ('components/tasks/DependencyBoard.tsx', 195, 'MISREPORT', '', "'No tasks on this board' (:327)"),
    ('components/tasks/DependencyBoard.tsx', 196, 'BLANK', '', 'agent colour map (:209)'),
    ('components/tasks/DependencyBoard.tsx', 200, 'BLANK', '', 'document-title lookup (:203)'),
    ('components/tasks/DependencyBoardView.tsx', 21, 'MISREPORT', '', "EmptyState 'No tasks yet' (:59-61) and an empty board picker (:71-82)"),
    ('components/tasks/TaskCard.tsx', 94, 'MISREPORT', 'PICKER', "`agentNames` (:95) is the assignee menu's option list"),
    ('components/tasks/TaskDetailDrawer.tsx', 35, 'SUPPRESSED', '', "`if (!canApprove || !data) return null` (:36) drops the 'Approving will not merge anything' warning"),
    ('components/tasks/TaskDetailDrawer.tsx', 146, 'SUPPRESSED', '', '`moves = allowed?.transitions?.[status] ?? []` (:191) — every status button disappears'),
    ('components/tasks/TaskDetailDrawer.tsx', 150, 'BLANK', '', 'assignee name list (:153)'),
    ('components/tasks/TaskDetailDrawer.tsx', 151, 'BLANK', '', 'document-path map (:158)'),
    ('components/tasks/TaskIntegrationNote.tsx', 36, 'SUPPRESSED', '', '`if (rows.length === 0) return null` (:39) removes the integration outcome and its retry button'),
    ('components/tasks/TasksBoard.tsx', 58, 'BLANK', '', 'colour map and assignee names (:62, :91)'),
    ('components/tasks/TasksBoard.tsx', 59, 'MISREPORT', '', "`transitions = allowed?.transitions ?? {}` (:96) makes the keyboard move announce 'No allowed status is available to the {direction} of {task}' (:124)"),
    ('hooks/useRequirementChips.ts', 25, 'BLANK', '', 'requirement-id to path map (:32)'),
]
# fmt: on

RENDERS = {
    ("hub/ui/src/" + path, line): (cls, flag, why) for path, line, cls, flag, why in CLASSIFIED
}

DECL_RE = re.compile(r"useQuery\s*[<(]")
EXPORT_FN_RE = re.compile(r"^export function (use\w+)")


def ts_files() -> list[Path]:
    return sorted(
        p for p in UI_SRC.rglob("*.ts*") if p.suffix in {".ts", ".tsx"} and ".test." not in p.name
    )


def rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


def comment_spans(text: str) -> list[tuple[int, int]]:
    """Where the comments are, so a hook *named in prose* is not counted as a call site.

    This is not pedantry: `JobCard.tsx:246` and `DependencyBoardView.tsx:16` both explain a fetch
    in a doc comment that writes the call out in full, and both were counted as call sites until
    this existed.
    """
    return [(m.start(), m.end()) for m in COMMENT_RE.finditer(text)]


def in_comment(spans: list[tuple[int, int]], pos: int) -> bool:
    return any(a <= pos < b for a, b in spans)


def balanced(text: str, start: int) -> str:
    """Return the object literal beginning at the first `{` at or after `start`."""
    i = text.index("{", start)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    return text[i:]


def statement_prefix(text: str, pos: int) -> str:
    """The text from the start of the enclosing statement up to `pos`.

    Call sites bind either by destructure (`const { data, error } = useX()`) or by name
    (`const q = useX()`), and the destructure is sometimes spread over several lines. Scanning
    back to the nearest statement keyword catches both without a TypeScript parser.
    """
    starts = [
        text.rfind(kw, max(0, pos - 600), pos) for kw in ("const ", "let ", "return ", "  var ")
    ]
    start = max(starts)
    if start < 0:
        start = text.rfind("\n", 0, pos) + 1
    return text[start:pos]


def declarations() -> list[dict]:
    """Every `useQuery` in `hub/ui/src/api/`, attributed to its exported hook."""
    out = []
    for path in sorted(API_DIR.glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        current = None
        current_start = 0
        for lineno, line in enumerate(lines, 1):
            m = EXPORT_FN_RE.match(line)
            if m:
                current = m.group(1)
                current_start = lineno
            if not DECL_RE.search(line):
                continue
            pos = sum(len(x) + 1 for x in lines[: lineno - 1]) + line.index("useQuery")
            opts = balanced(text, pos)
            prefix = statement_prefix(text, pos)
            out.append(
                {
                    "file": rel(path),
                    "line": lineno,
                    "hook": current,
                    "hook_line": current_start,
                    "returned_directly": prefix.strip().startswith("return"),
                    "poll": "refetchInterval" in opts,
                    "has_enabled": "enabled:" in opts,
                    "retry_disabled": bool(re.search(r"retry:\s*(false|0)", opts)),
                    "url": (
                        re.search(r"`(/api/v1[^`]*)`", opts).group(1)
                        if re.search(r"`(/api/v1[^`]*)`", opts)
                        else (
                            re.search(r"'(/api/v1[^']*)'", opts).group(1)
                            if re.search(r"'(/api/v1[^']*)'", opts)
                            else None
                        )
                    ),
                }
            )
    return out


def hook_bodies() -> dict[str, tuple[Path, str]]:
    """`useX` -> (file, source of the function body), for every exported hook in `api/`."""
    bodies = {}
    for path in sorted(API_DIR.glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^export function (use\w+)", text, re.M):
            name = m.group(1)
            nxt = text.find("\nexport ", m.end())
            bodies[name] = (path, text[m.start() : nxt if nxt > 0 else len(text)])
    return bodies


def exposes_error(name: str, body: str, decls: list[dict]) -> bool:
    """Can a caller of this hook reach the query's `error` at all?

    `return useQuery(...)` exposes the whole result. A hook that destructures the query and builds
    its own return object exposes only what that object names.
    """
    mine = [d for d in decls if d["hook"] == name]
    if any(d["returned_directly"] for d in mine):
        return True
    tail = body[body.rfind("return ") :] if "return " in body else ""
    return bool(re.search(r"\b(error|isError)\b", tail))


def call_sites(hooks: list[str], decl_files: set[str]) -> list[dict]:
    out = []
    for path in ts_files():
        text = path.read_text(encoding="utf-8")
        spans = comment_spans(text)
        for hook in hooks:
            for m in re.finditer(r"\b" + hook + r"\s*\(", text):
                if in_comment(spans, m.start()):
                    continue
                if rel(path) in decl_files and rel(path) == rel(API_DIR / f"{hook}.ts"):
                    continue
                prefix = statement_prefix(text, m.start())
                if "import" in prefix.split("\n")[0] and "from" in prefix:
                    continue
                if "export function " + hook in text[max(0, m.start() - 40) : m.start()]:
                    continue  # the declaration itself
                lineno = text.count("\n", 0, m.start()) + 1
                binds = bool(re.search(r"\b(error|isError)\b", prefix))
                alias = None
                am = re.search(r"\b(?:error|isError)\s*:\s*(\w+)", prefix)
                if am:
                    alias = am.group(1)
                elif binds:
                    alias = "error" if re.search(r"\berror\b", prefix) else "isError"
                named = re.match(r"const\s+(\w+)\s*=\s*$", prefix.strip() + " ".strip())
                obj = None
                nm = re.match(r"^\s*const\s+(\w+)\s*=\s*$", prefix)
                if nm:
                    obj = nm.group(1)
                if obj and not binds:
                    binds = bool(re.search(rf"\b{obj}\.(error|isError)\b", text))
                    alias = f"{obj}.error" if binds else None
                used = False
                if alias:
                    bare = alias.split(".")[0]
                    uses = len(re.findall(rf"\b{re.escape(bare)}\b", text))
                    used = uses > 1 if "." not in alias else uses > 1
                out.append(
                    {
                        "file": rel(path),
                        "line": lineno,
                        "hook": hook,
                        "binds_error": binds,
                        "alias": alias,
                        "error_used": used,
                        "named_binding": bool(named),
                    }
                )
    return out


def main() -> int:
    decls = declarations()
    bodies = hook_bodies()
    query_hooks = sorted({d["hook"] for d in decls if d["hook"]})
    decl_files = {d["file"] for d in decls}

    exposure = {h: exposes_error(h, bodies[h][1], decls) for h in query_hooks}
    sites = [s for s in call_sites(query_hooks, decl_files) if s["file"] not in decl_files]

    print(f"DECLARATIONS  {len(decls)} `useQuery` in {len(decl_files)} api files")
    print(f"QUERY HOOKS   {len(query_hooks)} exported hooks wrap at least one")
    print(
        f"  hooks that discard the error before any caller sees it: "
        f"{sum(1 for h in query_hooks if not exposure[h])}"
    )
    for h in query_hooks:
        if not exposure[h]:
            f, _ = bodies[h]
            print(f"      {h:32s} {rel(f)}")
    polls = {d["hook"] for d in decls if d["poll"]}
    print(f"  hooks with refetchInterval (polls): {len(polls)}")

    print(
        f"\nCALL SITES    {len(sites)} outside `api/`, in "
        f"{len({s['file'] for s in sites})} files"
    )
    handled = [s for s in sites if s["binds_error"] and s["error_used"]]
    bound_unused = [s for s in sites if s["binds_error"] and not s["error_used"]]
    unbound = [s for s in sites if not s["binds_error"]]
    print(f"  binds error and uses it (HANDLED):        {len(handled)}")
    print(f"  binds error and never uses it:            {len(bound_unused)}")
    print(f"  does not bind error:                      {len(unbound)}")
    unreachable = [s for s in unbound + bound_unused if not exposure[s["hook"]]]
    print(f"    of those, could not have (hook hides it): {len(unreachable)}")

    print("\nUNHANDLED SITES, by hand classification")
    buckets: dict[str, list[dict]] = {}
    for s in unbound + bound_unused:
        cls, flag, why = RENDERS.get((s["file"], s["line"]), ("UNCLASSIFIED", "", ""))
        s["why"], s["flag"] = why, flag
        buckets.setdefault(cls, []).append(s)
    for cls in ("MISREPORT", "SUPPRESSED", "BLANK", "NAMED", "UNCLASSIFIED"):
        rows = buckets.get(cls, [])
        poll_n = sum(1 for s in rows if s["hook"] in polls)
        flags = {}
        for s in rows:
            if s["flag"]:
                flags[s["flag"]] = flags.get(s["flag"], 0) + 1
        extra = "".join(f", {n} {f}" for f, n in sorted(flags.items()))
        print(f"  {cls:14s} {len(rows):3d}   ({poll_n} poll{extra})")
    mis = buckets.get("MISREPORT", [])
    live = [s for s in mis if s["flag"] != "DEAD"]
    pickers = [s for s in live if s["flag"] == "PICKER"]
    print(f"\n  MISREPORT on a surface an operator can reach: {len(live)}")
    print(f"    of those, an empty picker rather than a sentence: {len(pickers)}")
    print(f"    a sentence, a number or a terminal skeleton:      {len(live) - len(pickers)}")
    for s in sorted(buckets.get("UNCLASSIFIED", []), key=lambda s: (s["file"], s["line"])):
        print(f"      unclassified: {s['file']}:{s['line']} {s['hook']}")

    if "--context" in sys.argv:
        print("\nBINDING LINES (what each unhandled site does with the result)")
        for s in sorted(unbound + bound_unused, key=lambda s: (s["file"], s["line"])):
            line = (REPO / s["file"]).read_text(encoding="utf-8").split("\n")[s["line"] - 1]
            cls = RENDERS.get((s["file"], s["line"]), ("UNCLASSIFIED",))[0]
            print(f"  {cls:12s} {s['file']}:{s['line']}  {line.strip()}")

    if "--json" in sys.argv:
        print(json.dumps({"decls": decls, "sites": sites, "exposure": exposure}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
