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
  unhandled site is classified in `CLASSIFIED`, each entry naming its site by hook and
  occurrence (not by line, which drifts; see the note above the table) — the
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
#
# A row names its site by **hook and occurrence**, not by line: the `occurrence`-th call of `hook`
# in that file, counting in source order, 1-based. Until 2026-09-22 the key was the line number,
# and an edit anywhere above a site silently turned its row into a key nothing matched. That made
# the MISREPORT count fall with no surface repaired (F396): 19 rows had gone stale and one had
# landed on a different hook. The `(:N)` references inside the `why` text are prose, read off the
# tree each row was written against (`894b48e` for all but one), and they drift. The key does not.
# `stale_classifications` reports any row that no longer names an unhandled site, and
# `hub/tests/test_surface_ceilings.py` fails on one, so a repaired site has to take its row with it.
# One row per site, one line each: black would make this table 500 lines.
# fmt: off
CLASSIFIED: list[tuple[str, str, int, str, str, str]] = [
    # (path under hub/ui/src, hook, occurrence, class, flag, what it renders instead)
    ('App.tsx', 'useProjects', 1, 'MISREPORT', '', '`projects ?? []` reaches ProjectManagerModal (:598) and the current-project lookup (:234): an operator with projects is shown none'),
    ('App.tsx', 'useAgents', 1, 'MISREPORT', '', '`agents = []` is handed to the sidebar (:631) — the roster reads as empty'),
    ('App.tsx', 'useProjectConversations', 1, 'MISREPORT', '', "both behaviours at one site: `conversationsKnown` (:300) correctly treats undefined as 'not known yet', and `conversations={…?? []}` (:632) hands the tree an empty list"),
    ('App.tsx', 'useSpecDocuments', 1, 'MISREPORT', '', '`documents={specDocuments?.documents ?? []}` (:633)'),
    ('App.tsx', 'useTasks', 1, 'MISREPORT', '', '`tasks={allTasks ?? []}` (:634)'),
    ('components/accounting/AccountingPanel.tsx', 'useAccounting', 1, 'BLANK', '', '`if (!data) return null` (:16)'),
    ('components/accounting/AccountingPanel.tsx', 'useAccounting', 2, 'MISREPORT', '', "`if (isLoading || !data)` returns the Budgets skeleton (:34-42); `isLoading` is false after an error, so the skeleton is terminal — F197's shape exactly"),
    ('components/activity/ActivityLog.tsx', 'useAgents', 1, 'BLANK', '', 'agents only build a colour map (:62)'),
    ('components/agents/AgentActivityTab.tsx', 'useAgentOutput', 1, 'MISREPORT', '', "the merged feed renders 'No activity yet' (:112); this hook also hides its own error from every caller"),
    ('components/agents/AgentActivityTab.tsx', 'useAgentTimeline', 1, 'MISREPORT', '', 'same feed, same sentence (:112)'),
    ('components/agents/AgentCreateDialog.tsx', 'useModelCatalog', 1, 'MISREPORT', 'PICKER', '`providers = catalog?.providers ?? []` (:168) — the create dialog offers no provider'),
    ('components/agents/AgentCreateDialog.tsx', 'useProviderLaunchability', 1, 'SUPPRESSED', '', '`launchability?.[…]` (:84, :171) only decides whether a warning verdict is shown'),
    ('components/agents/AgentCreateDialog.tsx', 'useCharters', 1, 'MISREPORT', 'PICKER', '`charters.map` into `<option>` (:231)'),
    ('components/agents/AgentOutputPanel.tsx', 'useAgentOutput', 1, 'BLANK', '', 'only `isLoading` is taken and `lines` is deliberately unread (:148-152)'),
    ('components/agents/AgentOutputPanel.tsx', 'usePendingPermissionRequests', 1, 'SUPPRESSED', '', '`permissionRequests = []` (:1127): a run waiting on an approval renders no card'),
    ('components/agents/AgentOutputPanel.tsx', 'useQuestions', 1, 'SUPPRESSED', '', '`pendingQuestion` null (:206) and `questions={[]}` (:1129): a run waiting on an answer renders no ask'),
    ('components/agents/AgentOutputPanel.tsx', 'useAgentConversations', 1, 'MISREPORT', '', '`conversations = []` drives the list and `currentConversation` (:317)'),
    ('components/agents/AgentOutputPanel.tsx', 'useAgents', 1, 'MISREPORT', '', "`roster = []` (:1032) and the agent's own row missing (:321)"),
    ('components/agents/AgentOutputPanel.tsx', 'useRunners', 1, 'BLANK', '', '`runners` only resolves a label (:322)'),
    ('components/agents/AgentOutputPanel.tsx', 'useAccounting', 1, 'BLANK', '', '`recentTurns={accounting?.recent_turns}` (:1040) — the figure is absent'),
    ('components/agents/AgentOutputPanel.tsx', 'useConversationAccounting', 1, 'BLANK', '', '`{conversationUsage && …}` (:961)'),
    ('components/agents/AgentOutputPanel.tsx', 'useQueueStatus', 1, 'SUPPRESSED', '', '`queueStatus` undefined — the waiting indicator does not render'),
    ('components/agents/AgentOutputPanel.tsx', 'useQueuedEntries', 1, 'SUPPRESSED', '', '`hasQueuedWork` false (:343): queued work reads as none'),
    ('components/agents/AgentOutputPanel.tsx', 'useWorkspacePaths', 1, 'MISREPORT', 'PICKER', '`workspacePaths={[]}` (:1152)'),
    ('components/agents/AgentOutputPanel.tsx', 'useAgentChatHistory', 1, 'MISREPORT', '', '`timelineEntries = chat.data?.entries ?? []` (:350) — the transcript reads as empty'),
    ('components/agents/AgentOutputPanel.tsx', 'useAgentRecentChat', 1, 'MISREPORT', '', 'the same `chat` (:349-350) when no conversation is selected'),
    ('components/agents/AgentOutputPanel.tsx', 'useCheckpoints', 1, 'SUPPRESSED', '', '`offeredCheckpoint` undefined (:490) — the checkpoint offer does not render'),
    ('components/agents/AgentSettingsControls.tsx', 'useModelCatalog', 1, 'MISREPORT', 'PICKER', '`permissionModeValues(catalog)` (:180) yields no options'),
    ('components/agents/AgentSettingsControls.tsx', 'useRunners', 1, 'MISREPORT', 'PICKER', "'Loading runners…' is shown while `isLoading` (:224) and an empty select after the error (:242)"),
    ('components/agents/AgentSettingsControls.tsx', 'useCharters', 1, 'MISREPORT', 'PICKER', 'same shape for charters (:263, :282)'),
    ('components/agents/AgentSettingsPage.tsx', 'useAgents', 1, 'MISREPORT', '', "`roster.find` (:43) fails and the page renders 'This agent is no longer in the roster.' (:55)"),
    ('components/agents/AgentSettingsPage.tsx', 'useAgentSessions', 1, 'MISREPORT', '', "'No sessions yet.' (:451)"),
    ('components/agents/ComposerModelControls.tsx', 'useModelCatalog', 1, 'SUPPRESSED', '', 'the model controls do not render; the file states this intent for an undeclared provider (:167)'),
    ('components/agents/ConversationView.tsx', 'useSpecList', 1, 'MISREPORT', '', '`buildInventory(specList)` is empty (:119) and `specList={specList}` (:387) — the spec surface reads as having nothing in it'),
    ('components/agents/ConversationView.tsx', 'useAgentConversations', 1, 'BLANK', '', 'title lookup `?? null` (:114)'),
    ('components/agents/ConversationView.tsx', 'useWorkspacePaths', 1, 'MISREPORT', 'PICKER', '`paths={workspacePaths}` (:344)'),
    ('components/agents/ConversationView.tsx', 'useLoops', 1, 'MISREPORT', '', '`runningLoopCount(allLoops)` renders a 0 count on the Loops tab (:299)'),
    ('components/agents/NewConversationSurface.tsx', 'useAgents', 1, 'MISREPORT', '', '`roster.map` (:171) is the agent list this surface exists to show'),
    ('components/agents/NewConversationSurface.tsx', 'useRunners', 1, 'BLANK', '', 'runner label lookup (:60)'),
    ('components/agents/NewConversationSurface.tsx', 'useWorkspacePaths', 1, 'MISREPORT', 'PICKER', '`workspacePaths={…}` (:209)'),
    ('components/charters/ChartersPage.tsx', 'useCharters', 1, 'MISREPORT', '', "`charters.length === 0` renders EmptyState 'No charters yet' (:90-93)"),
    ('components/environment/DiagnosticsPanel.tsx', 'useStatus', 1, 'MISREPORT', '', '`JSON.stringify(data ?? {}, null, 2)` (:10) renders `{}` as the diagnostics'),
    ('components/environment/ProjectSettingsPanel.tsx', 'useProjects', 1, 'BLANK', '', '`projects.find` only names the project (:50)'),
    ('components/environment/ProjectSettingsPanel.tsx', 'useProjectSettings', 1, 'MISREPORT', '', '`if (!settings) return` (:67) leaves `form` unset, so the skeleton at :78 is terminal — this site *is* F197'),
    ('components/environment/ProjectSettingsPanel.tsx', 'useMainBranchSuggestion', 1, 'BLANK', '', "placeholder 'Not chosen' (:191); the suggestion button simply does not appear"),
    ('components/environment/ProjectSettingsPanel.tsx', 'useRunners', 1, 'MISREPORT', 'PICKER', 'runner selects (:170, :278)'),
    ('components/environment/ProjectSettingsPanel.tsx', 'useModelCatalog', 1, 'BLANK', '', '`catalog?.providers` optional at both uses (:91, :292)'),
    ('components/instructions/InstructionsPage.tsx', 'useProjects', 1, 'BLANK', '', "`projectName` falls back to 'this project' in the clear dialog (:156); nothing false is said"),
    ('components/jobs/JobCard.tsx', 'useTasks', 1, 'SUPPRESSED', '', '`canOpenQueue` false (:256) hides the open-queue button'),
    ('components/jobs/JobCard.tsx', 'useJobHistory', 1, 'MISREPORT', '', "RunHistory renders 'No runs yet' (:152-154) although its own comment (:146-147) says that claim must not be made before the answer arrives — the guard it added is `isLoading`, which is false on error"),
    ('components/jobs/JobForm.tsx', 'useAgents', 1, 'MISREPORT', 'PICKER', '`agents?.map` into `<option>` (:168)'),
    ('components/jobs/JobsPage.tsx', 'useJobs', 1, 'MISREPORT', '', "EmptyState 'No jobs yet — Create scheduled jobs to automatically trigger agents' (:133-138) and the totals row (:176-178)"),
    ('components/layout/AgentTree.tsx', 'useProjectConversations', 1, 'MISREPORT', '', "the tree's conversations (:62) and `archivedCount ?? 0` (:98)"),
    ('components/layout/AgentTree.tsx', 'useProjectConversations', 2, 'MISREPORT', '', "`archived.data?.conversations ?? []` (:72) behind the reason 'Nothing archived yet' (:116)"),
    ('components/layout/RecencyView.tsx', 'useProjectConversations', 1, 'MISREPORT', '', '`open.data?.conversations ?? []` (:55) and `archivedCount ?? 0` (:56)'),
    ('components/layout/RecencyView.tsx', 'useProjectConversations', 2, 'MISREPORT', '', "`archived.data?.conversations ?? []` (:57) behind 'Show archived (0)' (:150)"),
    ('components/layout/Sidebar.tsx', 'useProjects', 1, 'MISREPORT', '', "`projects.map` (:364, :504) is the sidebar's project list"),
    ('components/layout/StatusBar.tsx', 'useStatus', 1, 'MISREPORT', '', 'every count falls back to zero (:25-28): 0 pending messages, 0 active tasks, 0 unanswered questions, 0 agents'),
    ('components/layout/StatusBar.tsx', 'useAgents', 1, 'SUPPRESSED', '', '`contextWarningCount` (:21) drops to 0 and the context warning (:113) does not render'),
    ('components/layout/StatusBar.tsx', 'useAccounting', 1, 'SUPPRESSED', '', '`exhausted={accounting?.budget.exhausted ?? false}` (:122) — an exhausted budget renders no notice'),
    ('components/messages/MessagesFeed.tsx', 'useMessages', 1, 'MISREPORT', 'DEAD', "EmptyState 'No messages' (:143-145) — in a component nothing imports (F260), so no operator reaches it"),
    ('components/messages/MessagesFeed.tsx', 'useMessageHistory', 1, 'MISREPORT', 'DEAD', "EmptyState 'No message history' (:143-145), same dead component"),
    ('components/messages/MessagesFeed.tsx', 'useMessageHistory', 2, 'MISREPORT', 'DEAD', 'the agent filter built from `allMessages` (:27), same dead component'),
    ('components/overview/OverviewBudgetSummary.tsx', 'useAccounting', 1, 'MISREPORT', '', '`if (isLoading || !data)` returns a skeleton (:13) that is terminal after an error'),
    ('components/overview/OverviewPage.tsx', 'useAgents', 1, 'MISREPORT', '', "'No agents connected — Run `agentweave start` to connect agents.' (:145-147), which also tells the operator to do the wrong thing"),
    ('components/overview/OverviewPage.tsx', 'useQuestions', 1, 'SUPPRESSED', '', '`unanswered = questions.length` is 0 (:84) so the QuestionInterruptCard does not render (:130)'),
    ('components/overview/OverviewPage.tsx', 'useTasks', 1, 'MISREPORT', '', '`{taskCount} task` in the page header (:117) and the per-status counts (:86-91)'),
    ('components/overview/OverviewPage.tsx', 'useStatus', 1, 'BLANK', '', '`status?.project_name` is conditional (:118)'),
    ('components/projects/DirectoryPicker.tsx', 'useDirectoryListing', 1, 'MISREPORT', '', '\'No subdirectories\' (:162-163) — while the branch immediately above it renders the server\'s *stated* refusal, "Can\'t read this directory: {reason}" (:158-161)'),
    ('components/projects/DirectoryPicker.tsx', 'useFilesystemRoots', 1, 'MISREPORT', 'PICKER', '`roots = rootsData?.roots ?? []` (:47) leaves the roots strip empty'),
    ('components/projects/ProjectManagerModal.tsx', 'useNativeDialogAvailability', 1, 'BLANK', '', '`nativeAvailability?.available` (:141, :169) falls back to the manual path — deliberate degradation'),
    ('components/quality/QualityHealthPanel.tsx', 'useSessionSync', 1, 'MISREPORT', '', "EmptyState 'No quality governance configured' (:43-52) — a claim about the project's governance, made from a failed fetch"),
    ('components/quality/QualityHealthPanel.tsx', 'useTasks', 1, 'MISREPORT', '', "`(tasks ?? [])` filters render 'All reviewed tasks clear' (:103)"),
    ('components/questions/QuestionsPanel.tsx', 'useAgents', 1, 'BLANK', '', 'the per-agent timeout lookup (:143)'),
    ('components/runners/RunnersPage.tsx', 'useRunners', 1, 'MISREPORT', '', "`{!runners || runners.length === 0}` renders EmptyState 'No runners yet' (:81-84)"),
    ('components/runners/RunnersPage.tsx', 'useModelCatalog', 1, 'NAMED', '', "`catalogAvailable = !!catalog` (:202) renders 'The model catalog is unavailable — this runner will use the provider's default.' (:292). No `error` is bound and none is needed"),
    ('components/spec/SpecCoverageBar.tsx', 'useSpecCoverage', 1, 'BLANK', '', '`if (!data …) return null` (:87)'),
    ('components/spec/SpecDocumentPanel.tsx', 'useSpec', 1, 'MISREPORT', '', 'the `specDoc ? … : ` else branch is a second skeleton (:329-334), terminal after an error'),
    ('components/spec/SpecDocumentTasksLink.tsx', 'useSpecDocuments', 1, 'BLANK', '', '`if (!document …) return null` (:24)'),
    ('components/spec/SpecDocumentTasksLink.tsx', 'useDocumentTasks', 1, 'BLANK', '', 'same guard (:24)'),
    ('components/spec/SpecPage.tsx', 'useSpecList', 1, 'MISREPORT', '', "EmptyState 'Everything here is archived' (:98-107) — a failed spec-list fetch tells the operator their documents are archived"),
    ('components/spec/SpecPhaseBar.tsx', 'useSpecDocuments', 1, 'SUPPRESSED', '', '`if (!document) return null` (:33) removes the phase controls and the rigor refusal with it'),
    ('components/spec/SpecProposalsPanel.tsx', 'useSpecProposals', 1, 'SUPPRESSED', '', '`if (proposals.length === 0) return null` (:30) — pending edit proposals waiting on the operator do not render'),
    ('components/spec/SpecRailNav.tsx', 'useSpecList', 1, 'MISREPORT', '', "`buildInventory(specList)` (:31) leaves the rail's document list empty"),
    ('components/tasks/DependencyBoard.tsx', 'useTaskBoard', 1, 'MISREPORT', '', "'No tasks on this board' (:327)"),
    ('components/tasks/DependencyBoard.tsx', 'useAgents', 1, 'BLANK', '', 'agent colour map (:209)'),
    ('components/tasks/DependencyBoard.tsx', 'useTaskBoards', 1, 'BLANK', '', 'document-title lookup (:203)'),
    ('components/tasks/DependencyBoardView.tsx', 'useTaskBoards', 1, 'MISREPORT', '', "EmptyState 'No tasks yet' (:59-61) and an empty board picker (:71-82)"),
    ('components/tasks/TaskCard.tsx', 'useAgents', 1, 'MISREPORT', 'PICKER', "`agentNames` (:95) is the assignee menu's option list"),
    ('components/tasks/TaskDetailDrawer.tsx', 'useTaskIntegrationPreview', 1, 'SUPPRESSED', '', "`if (!canApprove || !data) return null` (:36) drops the 'Approving will not merge anything' warning"),
    ('components/tasks/TaskDetailDrawer.tsx', 'useAllowedTransitions', 1, 'SUPPRESSED', '', '`moves = allowed?.transitions?.[status] ?? []` (:191) — every status button disappears'),
    ('components/tasks/TaskDetailDrawer.tsx', 'useAgents', 1, 'BLANK', '', 'assignee name list (:153)'),
    ('components/tasks/TaskDetailDrawer.tsx', 'useSpecDocuments', 1, 'BLANK', '', 'document-path map (:158)'),
    ('components/tasks/TaskIntegrationNote.tsx', 'useTaskIntegrations', 1, 'SUPPRESSED', '', '`if (rows.length === 0) return null` (:39) removes the integration outcome and its retry button'),
    ('components/tasks/TasksBoard.tsx', 'useAgents', 1, 'BLANK', '', 'colour map and assignee names (:62, :91)'),
    ('components/tasks/TasksBoard.tsx', 'useAllowedTransitions', 1, 'MISREPORT', '', "`transitions = allowed?.transitions ?? {}` (:96) makes the keyboard move announce 'No allowed status is available to the {direction} of {task}' (:124)"),
    ('hooks/useRequirementChips.ts', 'useSpecDocuments', 1, 'BLANK', '', 'requirement-id to path map (:32)'),
]
# fmt: on

RENDERS = {
    ("hub/ui/src/" + path, hook, occurrence): (cls, flag, why)
    for path, hook, occurrence, cls, flag, why in CLASSIFIED
}
UNCLASSIFIED = ("UNCLASSIFIED", "", "")


def site_key(site: dict) -> tuple[str, str, int]:
    """The `RENDERS` key for a call site: its file, its hook, and which call of that hook it is."""
    return (site["file"], site["hook"], site["occurrence"])


# `useInfiniteQuery` too: the Logs hook became one (F252), and a pattern that saw only `useQuery`
# lost its call site from the count while the site still ignored its error.
DECL_RE = re.compile(r"use(?:Infinite)?Query\s*[<(]")
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
            decl = DECL_RE.search(line)
            if not decl:
                continue
            pos = sum(len(x) + 1 for x in lines[: lineno - 1]) + decl.start()
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
            occurrence = 0
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
                occurrence += 1
                out.append(
                    {
                        "file": rel(path),
                        "line": lineno,
                        "hook": hook,
                        "occurrence": occurrence,
                        "binds_error": binds,
                        "alias": alias,
                        "error_used": used,
                        "named_binding": bool(named),
                    }
                )
    return out


def unhandled_sites() -> list[dict]:
    """Every call site outside `api/` that does not bind and use the query's error.

    Split out of `main()` so the ratchet in `hub/tests/test_surface_ceilings.py` counts the same
    sites the report prints, rather than restating the sweep and drifting from it.
    """
    decls = declarations()
    query_hooks = sorted({d["hook"] for d in decls if d["hook"]})
    decl_files = {d["file"] for d in decls}
    sites = [s for s in call_sites(query_hooks, decl_files) if s["file"] not in decl_files]
    return [s for s in sites if not (s["binds_error"] and s["error_used"])]


def operator_reachable_misreports(unhandled: list[dict]) -> list[dict]:
    """The ceiling R-1 freezes: unhandled sites hand-classified MISREPORT on a live surface.

    `DEAD` is excluded because no operator can reach the surface; `PICKER` is not, because an
    empty picker is still a lie about why the list is empty.
    """
    out = []
    for s in unhandled:
        cls, flag, _why = RENDERS.get(site_key(s), UNCLASSIFIED)
        if cls == "MISREPORT" and flag != "DEAD":
            out.append(s)
    return out


def stale_classifications(unhandled: list[dict]) -> list[tuple[str, str, int]]:
    """`RENDERS` keys that name no unhandled site: a repaired site, or one whose hook was renamed.

    A stale row is how the MISREPORT count used to fall without a surface being repaired (F396),
    so the ratchet refuses to read the count while any row is stale.
    """
    live = {site_key(s) for s in unhandled}
    return sorted(key for key in RENDERS if key not in live)


def unclassified_sites(unhandled: list[dict]) -> list[dict]:
    """Unhandled sites no row names. That is a new site, or one displaced by a new call above it.

    The second case is why this is checked and not only printed. A new unhandled call of a hook,
    inserted above a classified call of the same hook in the same file, takes over the old site's
    `occurrence` and so its row. The old site then shows up here, not as a stale row.
    """
    return [s for s in unhandled if site_key(s) not in RENDERS]


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
        cls, flag, why = RENDERS.get(site_key(s), UNCLASSIFIED)
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
    live = operator_reachable_misreports(unbound + bound_unused)
    pickers = [s for s in live if s["flag"] == "PICKER"]
    print(f"\n  MISREPORT on a surface an operator can reach: {len(live)}")
    print(f"    of those, an empty picker rather than a sentence: {len(pickers)}")
    print(f"    a sentence, a number or a terminal skeleton:      {len(live) - len(pickers)}")
    for s in sorted(buckets.get("UNCLASSIFIED", []), key=lambda s: (s["file"], s["line"])):
        print(f"      unclassified: {s['file']}:{s['line']} {s['hook']} #{s['occurrence']}")
    for file, hook, occurrence in stale_classifications(unbound + bound_unused):
        print(f"      stale row (no unhandled site): {file} {hook} #{occurrence}")

    if "--context" in sys.argv:
        print("\nBINDING LINES (what each unhandled site does with the result)")
        for s in sorted(unbound + bound_unused, key=lambda s: (s["file"], s["line"])):
            line = (REPO / s["file"]).read_text(encoding="utf-8").split("\n")[s["line"] - 1]
            cls = RENDERS.get(site_key(s), UNCLASSIFIED)[0]
            print(f"  {cls:12s} {s['file']}:{s['line']}  {line.strip()}")

    if "--json" in sys.argv:
        print(json.dumps({"decls": decls, "sites": sites, "exposure": exposure}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
