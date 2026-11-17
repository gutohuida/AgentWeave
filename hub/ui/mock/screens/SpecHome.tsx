import * as React from 'react'
import { Segmented } from '@/components/ui/segmented'
import { SpecHome as Home, type HomeBuild, type HomeCapability, type RelationsView } from '@/components/spec/home/SpecHome'
import { toast } from '@/lib/toast'
import '@/styles/spec-page.css'

// mock state: the builds are this repository's real ones as the trial Hub held them on 2026-11-17
// (titles, roadmaps, slices, capabilities, task counts, finish times and costs); the capabilities'
// waiting counts are written by hand.

const NOW = new Date('2026-11-17T10:30:00Z')

const RM = {
  checks: { path: 'spec/changes/checks-that-land-work-fast-and-blame-fairly/spec.json', title: 'Checks that land work fast and blame fairly' },
  nav: { path: 'spec/changes/spec-visuals-and-navigability-roadmap/spec.json', title: 'Spec visuals and navigability' },
  desktop: { path: 'spec/changes/agentweave-feels-like-a-desktop-app/spec.json', title: 'AgentWeave feels like a desktop app' },
  panel: { path: 'spec/changes/a-side-panel-worth-keeping-open-activity-changes-files-terminal-and-peers/spec.json', title: 'A side panel worth keeping open' },
}
const cap = (name: string, title: string) => ({ path: `spec/capabilities/${name}/spec.json`, title })
const CAP = {
  checks: cap('project-checks', 'Project checks'),
  roadmaps: cap('spec-roadmaps', 'Spec roadmaps'),
  page: cap('spec-page', 'Spec page'),
  lifecycle: cap('app-lifecycle', 'App lifecycle'),
  authority: cap('spec-document-authority', 'Spec document authority'),
  builds: cap('builds', 'Builds'),
  panel: cap('conversation-side-panel', 'Conversation side panel'),
  dashboards: cap('project-dashboards', 'Project dashboards'),
}
const doc = (name: string, title: string) => ({ path: `spec/changes/${name}/spec.json`, title })

let n = 0
function build(
  state: HomeBuild['state'],
  document: { path: string; title: string },
  roadmap: [{ path: string; title: string }, string, string] | null,
  capabilities: Array<{ path: string; title: string }>,
  tasks: [number, number, number],
  startedAt: string,
  finishedAt: string | null,
  spentUsd: number | null,
): HomeBuild {
  return {
    id: `build-${++n}`,
    state,
    document,
    roadmap: roadmap ? { document: roadmap[0], slice: { key: roadmap[1], title: roadmap[2] } } : null,
    capabilities,
    tasksDone: tasks[0],
    tasksTotal: tasks[1],
    tasksLanding: tasks[2],
    startedAt,
    finishedAt,
    spentUsd,
  }
}

// Newest build first, as GET /project/builds returns them.
const BUILDS: HomeBuild[] = [
  build('running', doc('a-check-that-cannot-run-says-so-and-is-never-silently-excused', 'A check that cannot run says so and is never silently excused'), [RM.checks, 'a-check-that-cannot-run-says-so', 'A check that cannot run says so'], [CAP.checks], [0, 3, 0], '2026-11-17T08:52:35Z', null, null),
  build('finished', doc('a-landing-failure-is-blamed-on-a-task-only-when-it-reproduces-there', 'A landing failure is blamed on a task only when it reproduces there'), [RM.checks, 'blame-only-what-reproduces', 'Blame only what reproduces'], [CAP.checks], [5, 5, 0], '2026-11-16T22:39:59Z', '2026-11-17T03:09:58Z', 26.96),
  build('finished', doc('a-roadmap-that-is-recognisably-a-roadmap', 'A roadmap that is recognisably a roadmap'), [RM.nav, 'roadmap-page', 'A roadmap that is recognisably a roadmap'], [CAP.roadmaps, CAP.page], [6, 6, 0], '2026-11-16T22:39:55Z', '2026-11-17T01:58:42Z', 22.82),
  build('finished', doc('ready-means-the-same-thing-to-the-author-and-the-operator', 'Ready means the same thing to the author and the operator'), [RM.nav, 'one-readiness', 'Ready means the same thing'], [CAP.authority, CAP.page], [5, 5, 0], '2026-11-16T09:59:00Z', '2026-11-16T16:22:44Z', 24.42),
  build('finished', doc('a-development-checkout-updates-the-same-way', 'A development checkout updates the same way'), [RM.desktop, 'updates-a-checkout', 'A development checkout updates the same way'], [CAP.lifecycle], [6, 6, 0], '2026-11-16T08:47:32Z', '2026-11-16T21:15:17Z', 32.64),
  build('finished', doc('spec-page-remembers-readable-task-threads-retrospective-after-landing', 'Remembered spec, readable task threads, retrospective after landing'), [RM.nav, 'quick-wins', 'Quick wins'], [CAP.page, CAP.builds], [4, 4, 0], '2026-11-15T21:24:07Z', '2026-11-16T00:30:34Z', 11.96),
  build('finished', doc('agentweave-updates-itself', 'AgentWeave updates itself'), [RM.desktop, 'updates-itself', 'AgentWeave updates itself'], [CAP.lifecycle], [5, 5, 0], '2026-11-15T19:55:51Z', '2026-11-16T03:01:08Z', 29.46),
  build('finished', doc('the-watch-tab-shows-what-the-agent-is-doing-with-colour-and-motion', 'The Watch tab shows what the agent is doing with colour and motion'), null, [CAP.panel], [2, 2, 0], '2026-11-15T14:54:41Z', '2026-11-15T15:58:22Z', 5.58),
  build('finished', doc('the-side-panel-s-watch-tab-follows-another-agent-s-conversation-live', "The side panel's Watch tab follows another agent's conversation live"), [RM.panel, 'peer-conversation', 'Watch another agent'], [CAP.panel], [4, 4, 0], '2026-11-15T12:40:44Z', '2026-11-15T14:14:02Z', 8.7),
  build('finished', doc('a-terminal-in-the-side-panel', 'A terminal in the side panel'), [RM.panel, 'terminal-tab', 'A terminal in the panel'], [CAP.panel], [8, 8, 0], '2026-11-14T12:10:33Z', '2026-11-15T04:59:23Z', 56.54),
  build('finished', doc('dashboards-that-feel-alive-and-draw-right-the-first-time', 'Dashboards that feel alive and draw right the first time'), null, [CAP.dashboards], [6, 6, 0], '2026-11-14T11:42:12Z', '2026-11-15T01:10:54Z', 32.98),
]

const CAPABILITIES: HomeCapability[] = [
  { ...CAP.panel, waiting: 3 },
  { ...CAP.page, waiting: 3 },
  { ...CAP.lifecycle, waiting: 2 },
  { ...CAP.checks, waiting: 2 },
  { ...CAP.roadmaps, waiting: 1 },
  { ...CAP.authority, waiting: 1 },
  { ...CAP.builds, waiting: 1 },
  { ...CAP.dashboards, waiting: 1 },
  { ...cap('agent-flows', 'Agent flows'), waiting: 0 },
  { ...cap('knowledge-vault', 'Knowledge vault'), waiting: 0 },
  { ...cap('task-board', 'Task board'), waiting: 0 },
  { ...cap('landing-queue', 'Pull request landing'), waiting: 0 },
]

const NOTES: Record<RelationsView, string> = {
  links:
    'A — Links on each row. Every build names its roadmap › slice and the capabilities it changes, each one click away. Cheapest to build and to read row by row; the relations between rows are not shown, so seeing that three builds touched the same capability means scanning.',
  tree:
    'B — An outline. The same builds regrouped under their roadmaps, slice by slice, with the capabilities each changes beneath it. Shows which builds belong together; a capability touched from two roadmaps appears twice. Hover anything to light what it connects to.',
  map:
    'C — A drawn map. Roadmaps, the shown builds and their capabilities in three columns joined by threads; hover a roadmap, build or capability to light everything it connects to. Shows shared capabilities at a glance; the most to build, and it grows tall as more builds are shown.',
}

export default function SpecHome() {
  const [relations, setRelations] = React.useState<RelationsView>('links')
  return (
    <div className="mock-threads">
      <div className="mock-threads-bar">
        <Segmented
          label="How it relates"
          value={relations}
          onChange={setRelations}
          options={[
            { value: 'links', label: 'A · Links on rows' },
            { value: 'tree', label: 'B · Outline' },
            { value: 'map', label: 'C · Drawn map' },
          ]}
        />
      </div>
      <p className="mock-threads-note">{NOTES[relations]}</p>
      <Home
        builds={BUILDS}
        capabilities={CAPABILITIES}
        relations={relations}
        now={NOW}
        onOpen={(path, anchor) => toast({ title: anchor ? 'Opens the roadmap at that slice' : 'Opens the document', description: path })}
      />
      <p className="mock-threads-note" style={{ marginTop: 28 }}>
        The existing document list follows here, with its search, filters and order unchanged.
      </p>
    </div>
  )
}
