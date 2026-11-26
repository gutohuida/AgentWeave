import * as React from "react";
import { useAgents } from "@/api/agents";
import { readableApiError } from "@/api/client";
import {
  useClearStableFixTasks,
  useDisturbedRuns,
  useKnownFailing,
} from "@/api/knownFailing";
import {
  recordOverviewVisit,
  refreshOverviewNote,
  useOverview,
  type OverviewBody,
} from "@/api/overview";
import { useProjects } from "@/api/projects";
import {
  useQuarantine,
  useRemoveNeverQuarantine,
  useSetNeverQuarantine,
} from "@/api/quarantine";
import { Icon } from "@/components/common/Icon";
import { QueryErrorNotice } from "@/components/common/QueryErrorNotice";
import { agentColorVars } from "@/lib/agentColors";
import { buildDestination, goTo } from "@/lib/navigation";
import { useConfigStore } from "@/store/configStore";
import {
  selectOpeningTab,
  useOverviewTabsStore,
  type OverviewTabId,
} from "@/store/overviewTabsStore";
import { AgentPostureChips } from "./AgentPostureChips";
import { KnownFailingList } from "./KnownFailingList";
import { OverviewClassicScreen } from "./OverviewClassicScreen";
import { OverviewBriefing, type BriefingNote } from "./OverviewBriefing";
import {
  OverviewDashboard,
  type DashActivity,
  type DashBuild,
  type DashNeed,
} from "./OverviewDashboard";
import {
  dashboardFigures,
  finishedCostWords,
  overviewPanelDomId,
  overviewTabDomId,
  useOverviewOpeners,
  type OverviewScreenProps,
} from "./overviewLiveModel";
import { OverviewTabs } from "./OverviewTabs";
import { ProjectSetupList } from "./ProjectSetupList";
import { QuarantineList } from "./QuarantineList";
import "@/styles/overview-tabs.css";

/** The project Overview (`overview-at-a-glance-with-dashboard-and-briefing-tabs`): two tabs over
 *  one Hub read (`GET /overview`, design D1). The Dashboard is live here; the Briefing is wired by
 *  its own task. A Hub older than the route answers 404, and the previous Overview is shown under a
 *  notice to restart, so a committed bundle never meets a blank page (design, hazards). */

export function OverviewScreen(props: OverviewScreenProps) {
  const projectId = useConfigStore((state) => state.selectedProjectId);
  const overview = useOverview();
  if (!projectId) return null;
  if (overview.data === null) {
    // A Hub started before this Overview: say what to do, and keep what it can show.
    return (
      <div className="aw-ov-live">
        <p className="aw-ov-restart" role="status" data-slot="overview-restart">
          <Icon name="restart_alt" size={16} /> Restart the Hub to see the new
          Overview.
        </p>
        <OverviewClassicScreen {...props} />
      </div>
    );
  }
  return (
    <LiveOverview projectId={projectId} overview={overview} screen={props} />
  );
}

function LiveOverview({
  projectId,
  overview,
  screen,
}: {
  projectId: string;
  overview: ReturnType<typeof useOverview>;
  screen: OverviewScreenProps;
}) {
  const opening = useOverviewTabsStore((s) => selectOpeningTab(s, projectId));
  const openTab = useOverviewTabsStore((s) => s.openTab);
  const [active, setActive] = React.useState<OverviewTabId>(opening);
  // Another project keeps its own tabs: switching project re-reads where this one opens.
  const openingRef = React.useRef(opening);
  openingRef.current = opening;
  React.useEffect(() => {
    setActive(
      useOverviewTabsStore.getState().session[projectId] ?? openingRef.current,
    );
  }, [projectId]);
  // The operator opened the Overview: the Hub records the visit (and may start a note), then the
  // read is taken again so "since you last looked" counts from the visit before this one.
  const { refetch } = overview;
  React.useEffect(() => {
    let live = true;
    void recordOverviewVisit(projectId).then(() => {
      if (live) void refetch();
    });
    return () => {
      live = false;
    };
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  const choose = (tab: OverviewTabId) => {
    setActive(tab);
    openTab(projectId, tab);
  };

  return (
    <div className="aw-ov-live" data-slot="overview-live">
      <div className="aw-ov-live-head">
        <ProjectSetupList place="overview" />
        <OverviewTabs projectId={projectId} active={active} onOpen={choose} />
      </div>
      <div
        role="tabpanel"
        id={overviewPanelDomId(active)}
        aria-labelledby={overviewTabDomId(active)}
        data-tab={active}
      >
        {overview.error ? (
          <div className="aw-ov-placeholder">
            <QueryErrorNotice
              failures={[["the Overview", overview.error, overview.refetch]]}
            />
          </div>
        ) : !overview.data ? (
          <p className="aw-ov-placeholder" role="status">
            Loading the Overview…
          </p>
        ) : active === "dashboard" ? (
          <LiveDashboard
            projectId={projectId}
            body={overview.data}
            screen={screen}
          />
        ) : (
          <LiveBriefing
            projectId={projectId}
            body={overview.data}
            screen={screen}
            refetch={overview.refetch}
          />
        )}
      </div>
    </div>
  );
}

/** Both tabs' items, mapped from the one read the same way, so a figure on one never contradicts the
 *  other (FR-10). `todays` is what the Dashboard's timeline lists; `finishedAll` is what the Briefing
 *  counts from the last visit. */
function useOverviewItems(
  projectId: string,
  body: OverviewBody,
  screen: OverviewScreenProps,
) {
  const {
    data: agents = [],
    error: agentsError,
    refetch: refetchAgents,
  } = useAgents();
  const open = useOverviewOpeners(projectId, screen);
  const now = new Date();
  const colorOf = (name: string | null) =>
    name ? agents.find((a) => a.name === name)?.color_index : undefined;
  const { main, spend, finishedToday, todays } = dashboardFigures(body, now);

  const needs: DashNeed[] = body.needs.map((n) => ({
    id: n.id,
    kind: n.kind,
    agent: n.agent,
    colorIndex: colorOf(n.agent),
    title: n.title,
    action: n.action,
    at: n.waiting_since,
    onOpen: () => open.openTarget(n.target, n.agent),
  }));
  const running: DashActivity[] = body.running.map((r) => ({
    id: `run-${r.run_id}`,
    agent: r.agent,
    colorIndex: colorOf(r.agent),
    what: r.what,
    outcome: "running",
    at: r.started_at,
    stage: r.stage ?? null,
    check: r.check_state ?? null,
    onOpen: () => open.openConversation(r.agent, r.conversation_id),
  }));
  const toActivity = (f: OverviewBody["finished"][number]): DashActivity => ({
    id: `finished-${f.id}`,
    agent: f.agent ?? "The Hub",
    colorIndex: colorOf(f.agent),
    what: f.title,
    outcome: f.outcome,
    at: f.at,
    usd: f.usd,
    costWords: finishedCostWords(f),
    onOpen: () =>
      f.task_id
        ? open.openTask(f.task_id)
        : f.agent
          ? screen.onNavigate(`agent:${f.agent}`)
          : screen.onNavigate("activity"),
  });
  // The timeline lists today's finished work (FR-7); the Briefing counts from the last visit.
  const finished = todays.map(toActivity);
  const finishedAll = body.finished.map(toActivity);
  const builds: DashBuild[] = body.builds.map((b) => ({
    id: b.build_id,
    title: b.title,
    done: b.tasks_done,
    total: b.tasks_total,
    stage: b.stage_words,
    needsYou: b.needs_operator,
    onOpen: () => goTo(buildDestination(projectId, b.build_id)),
  }));
  return {
    open,
    now,
    main,
    spend,
    finishedToday,
    needs,
    running,
    finished,
    finishedAll,
    builds,
    agentsError,
    refetchAgents,
  };
}

function LiveDashboard({
  projectId,
  body,
  screen,
}: {
  projectId: string;
  body: OverviewBody;
  screen: OverviewScreenProps;
}) {
  // A failed read of either only loses a name or a colour; say so rather than show them blank.
  const {
    data: projects = [],
    error: projectsError,
    refetch: refetchProjects,
  } = useProjects();
  const {
    open,
    now,
    main,
    spend,
    finishedToday,
    needs,
    running,
    finished,
    builds,
    agentsError,
    refetchAgents,
  } = useOverviewItems(projectId, body, screen);

  return (
    <>
      <QueryErrorNotice
        failures={[
          ["the project list", projectsError, refetchProjects],
          ["the profiles", agentsError, refetchAgents],
        ]}
      />
      <OverviewDashboard
        projectName={projects.find((p) => p.id === projectId)?.name ?? ""}
        needs={needs}
        running={running}
        finished={finished}
        finishedToday={finishedToday}
        spend={spend}
        main={main}
        builds={builds}
        onNavigate={open.openPlace}
        now={now}
      >
        <ChecksAndProfiles
          onNavigate={screen.onNavigate}
          onOpenTask={open.openTask}
        />
      </OverviewDashboard>
    </>
  );
}

function LiveBriefing({
  projectId,
  body,
  screen,
  refetch,
}: {
  projectId: string;
  body: OverviewBody;
  screen: OverviewScreenProps;
  refetch: () => unknown;
}) {
  const {
    data: projects = [],
    error: projectsError,
    refetch: refetchProjects,
  } = useProjects();
  const {
    open,
    now,
    main,
    spend,
    finishedToday,
    needs,
    running,
    finishedAll,
    builds,
  } = useOverviewItems(projectId, body, screen);
  const [refreshing, setRefreshing] = React.useState(false);
  const [refusal, setRefusal] = React.useState<string | null>(null);
  const refresh = () => {
    setRefreshing(true);
    setRefusal(null);
    void refreshOverviewNote(projectId).then((reason) => {
      setRefusal(reason);
      setRefreshing(false);
      void refetch();
    });
  };
  const attempt = body.note_last_attempt;
  const failedAttempt =
    attempt && attempt.outcome !== "written" ? attempt : null;
  const note: BriefingNote = {
    writtenAt: body.note?.written_at ?? "",
    text: body.note?.text ?? "",
    links: (body.note?.cites ?? []).map((c) => ({
      key: `${c.type}:${c.id}`,
      label: c.label,
      onOpen: () => {
        if (c.type === "task") open.openTask(c.id);
        else if (c.type === "build") goTo(buildDestination(projectId, c.id));
        else if (c.type === "profile") screen.onNavigate(`agent:${c.id}`);
        else screen.onNavigate("questions");
      },
    })),
    writing: body.note_writing,
    // A refusal the button just met, else why the latest firing wrote none; the earlier note stays.
    problem:
      refusal ??
      (failedAttempt
        ? (failedAttempt.reason ?? "The note could not be written.")
        : null),
    refreshing,
    onRefresh: refresh,
  };
  return (
    <>
      <QueryErrorNotice
        failures={[["the project list", projectsError, refetchProjects]]}
      />
      <OverviewBriefing
        projectName={projects.find((p) => p.id === projectId)?.name ?? ""}
        lastSeenAt={body.visit?.previous_at ?? null}
        needs={needs}
        running={running}
        finished={finishedAll}
        finishedToday={finishedToday}
        spend={spend}
        main={main}
        builds={builds}
        onNavigate={open.openPlace}
        now={now}
        note={note}
      />
    </>
  );
}

type MorePanel = "checks" | "profiles";

/** The previous Overview's quarantine list, known-failing list and profile status chips, reached by
 *  a link each (FR-13). Each list's hooks run only while it is open. */
export function ChecksAndProfiles({
  onNavigate,
  onOpenTask,
}: {
  onNavigate: (page: string) => void;
  onOpenTask: (taskId: string) => void;
}) {
  const [panel, setPanel] = React.useState<MorePanel | null>(null);
  const toggle = (next: MorePanel) =>
    setPanel((current) => (current === next ? null : next));
  return (
    <section className="aw-ov-more" aria-label="Checks and profiles">
      <div className="aw-ov-more-links">
        <button
          type="button"
          data-slot="overview-more-link"
          className="aw-ov-more-link"
          aria-expanded={panel === "checks"}
          aria-controls="overview-more-checks"
          onClick={() => toggle("checks")}
        >
          <Icon name="verified_user" size={15} /> Quarantine and known failures
        </button>
        <button
          type="button"
          data-slot="overview-more-link"
          className="aw-ov-more-link"
          aria-expanded={panel === "profiles"}
          aria-controls="overview-more-profiles"
          onClick={() => toggle("profiles")}
        >
          <Icon name="group" size={15} /> Profile status
        </button>
      </div>
      {panel === "checks" ? <ChecksPanel onOpenTask={onOpenTask} /> : null}
      {panel === "profiles" ? <ProfilesPanel onNavigate={onNavigate} /> : null}
    </section>
  );
}

function ChecksPanel({ onOpenTask }: { onOpenTask: (taskId: string) => void }) {
  const now = new Date();
  const {
    data: knownFailing,
    error: knownFailingError,
    refetch: refetchKnownFailing,
  } = useKnownFailing();
  const { data: disturbedRuns = [] } = useDisturbedRuns();
  const clearStable = useClearStableFixTasks();
  const {
    data: quarantine,
    error: quarantineError,
    refetch: refetchQuarantine,
  } = useQuarantine();
  const setMark = useSetNeverQuarantine();
  const removeMark = useRemoveNeverQuarantine();
  return (
    <div
      id="overview-more-checks"
      className="aw-ov-more-panel"
      data-slot="overview-quarantine"
    >
      <h2>Quarantine and known failures</h2>
      <QueryErrorNotice
        failures={[
          ["the known-failing list", knownFailingError, refetchKnownFailing],
          ["the quarantine", quarantineError, refetchQuarantine],
        ]}
      />
      {knownFailing ? (
        <KnownFailingList
          entries={knownFailing}
          disturbed={disturbedRuns}
          onClear={() => clearStable.mutate()}
          clearing={clearStable.isPending}
          cleared={clearStable.data ?? null}
          clearError={
            clearStable.error
              ? readableApiError(
                  clearStable.error,
                  "The fix tasks could not be closed.",
                )
              : null
          }
          onOpenTask={onOpenTask}
          now={now}
        />
      ) : null}
      {quarantine ? (
        <QuarantineList
          quarantined={quarantine.quarantined}
          marks={quarantine.marks}
          onSetMark={(check, test) => setMark.mutate({ check, test })}
          onRemoveMark={(check, test) => removeMark.mutate({ check, test })}
          busy={setMark.isPending || removeMark.isPending}
          error={
            setMark.error
              ? readableApiError(setMark.error, "The mark could not be set.")
              : removeMark.error
                ? readableApiError(
                    removeMark.error,
                    "The mark could not be removed.",
                  )
                : null
          }
          onOpenTask={onOpenTask}
          now={now}
        />
      ) : null}
    </div>
  );
}

function ProfilesPanel({ onNavigate }: { onNavigate: (page: string) => void }) {
  const { data: agents = [], error, refetch } = useAgents();
  return (
    <div
      id="overview-more-profiles"
      className="aw-ov-more-panel"
      data-slot="overview-profile-status"
    >
      <h2>Profile status</h2>
      <QueryErrorNotice failures={[["the profiles", error, refetch]]} />
      <ul className="aw-ov-profile-list">
        {agents.map((a) => (
          <li key={a.name} className="aw-ov-profile">
            <span className="aw-ov-profile-name">
              <span
                className="aw-od-agent-dot"
                style={{ background: agentColorVars(a.color_index).accent }}
                aria-hidden
              />
              {a.name}
            </span>
            <AgentPostureChips agent={a} onNavigate={onNavigate} />
          </li>
        ))}
      </ul>
    </div>
  );
}
