import * as React from 'react'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'
import { Toaster } from '@/components/ui/toast'
import { APP_SETTINGS_SECTIONS, PROJECT_TABS, type AppSettingsSection, type ProjectTab } from '@/lib/navigation'
import { PROFILES_MOCK_STATES, useProfilesAddress, type ProfilesMockState } from './profilesMock'
import { MOCK_NOW, project, projects, tasks } from './fixtures'
import { BUILD_MOCK_STATES, DEFAULT_BUILD, RECORDED_BUILDS, useBuildHash, type BuildMockState } from './buildsMock'
import { beforeKey, type MockRoute } from './routes'
import { SCREENS, screenFor } from './screens'
import { useSetupTitles } from './setupMock'
import { SIDEBAR_MOCK_STATES, setSidebarMockState, useBuildsNeedingYou, useSidebarMock, useSidebarProjectBody, type SidebarMockState } from './sidebarMock'
import { LEANER_TABS } from './leanerMock'
import { NOTICE_LEVELS } from './specBanner'
import { SPEC_MOCK_STATES, setSpecMockControls, useSpecMockControls } from './specMock'
import { setTasksMockControls, useTasksMockControls } from './tasksMock'

/** The tabs the mock's top bar lists: the app's own, with Profiles after Tasks (operator, 2026-11-21).
 *  Profiles is not in the app's PROJECT_TABS until the page is wired in. */
/** Every tab a hash may name; the top bar lists only LEANER_TABS (leaner-navigation: the others moved into a thread's side panel, a profile's page and project settings). */
const MOCK_TABS: readonly ProjectTab[] = PROJECT_TABS.flatMap((t): ProjectTab[] => (t === 'tasks' ? [t, 'profiles'] : [t]))

const BEFORE = import.meta.glob('./before/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>

function parseHash(): MockRoute {
  // A query after the route (`?state=…&layout=…&at=…`) presets a screen's mock controls.
  const raw = decodeURIComponent(window.location.hash.replace(/^#/, '')).split('?')[0]!
  const [kind, a, b, c] = raw.split('/')
  if (kind === 'tab' && a === 'overview-next') {
    const state = new URLSearchParams(decodeURIComponent(window.location.hash).split('?')[1] ?? '').get('state')
    return { kind: 'overview-next', state: state === 'quiet' || state === 'trouble' ? state : 'busy' }
  }
  if (kind === 'tab' && (MOCK_TABS as readonly string[]).includes(a ?? '')) return { kind: 'tab', tab: a as ProjectTab }
  if (kind === 'conversation' && a) return { kind: 'conversation', agent: a, conversationId: b || null, ...(c && PANELS.has(c) ? { panel: c as NonNullable<Extract<MockRoute, { kind: 'conversation' }>['panel']> } : {}) }
  if (kind === 'settings') return { kind: 'settings', section: (a as never) || 'general' }
  if (kind === 'agent-settings' && a) return { kind: 'agent-settings', agent: a, section: (b as never) || 'running' }
  if (kind === 'app-settings') {
    const section = (APP_SETTINGS_SECTIONS as readonly string[]).includes(a ?? '') ? (a as AppSettingsSection) : 'notifications'
    return { kind: 'app-settings', section }
  }
  if (kind === 'gallery') return { kind: 'gallery' }
  if (kind === 'task-redesign') return { kind: 'task-redesign' }
  if (kind === 'task-threads') return { kind: 'task-threads' }
  if (kind === 'roadmap') return { kind: 'roadmap' }
  if (kind === 'spec-home') return { kind: 'spec-home' }
  if (kind === 'spec-thread-ui') return { kind: 'spec-thread-ui' }
  if (kind === 'first-run-polish') return { kind: 'first-run-polish' }
  if (kind === 'thread') return { kind: 'thread' }
  if (kind === 'traces') return { kind: 'traces' }
  if (kind === 'conversation-trace') return { kind: 'conversation-trace', conversationId: a || null }
  if (kind === 'build') return { kind: 'build', buildId: a || null }
  if (kind === 'build-summaries') return { kind: 'build-summaries' }
  if (kind === 'profile-pools') return { kind: 'profile-pools', view: a === 'chat' ? 'chat' : 'build' }
  return { kind: 'tab', tab: 'overview' }
}

function toHash(route: MockRoute): string {
  switch (route.kind) {
    case 'tab':
      return `tab/${route.tab}${route.profile ? `?profile=${encodeURIComponent(route.profile)}` : ''}`
    case 'conversation':
      return `conversation/${route.agent}/${route.conversationId ?? ''}${route.panel ? `/${route.panel}` : ''}`
    case 'settings':
      return `settings/${route.section}`
    case 'agent-settings':
      return `agent-settings/${route.agent}/${route.section}`
    case 'app-settings':
      return `app-settings/${route.section}`
    case 'gallery':
      return 'gallery'
    case 'task-redesign':
      return 'task-redesign'
    case 'task-threads':
      return 'task-threads'
    case 'roadmap':
      return 'roadmap'
    case 'spec-home':
      return 'spec-home'
    case 'spec-thread-ui':
      return 'spec-thread-ui'
    case 'first-run-polish':
      return 'first-run-polish'
    case 'overview-next':
      return route.state === 'busy' ? 'tab/overview-next' : `tab/overview-next?state=${route.state}`
    case 'thread':
      return 'thread'
    case 'traces':
      return 'traces'
    case 'conversation-trace':
      return `conversation-trace/${route.conversationId ?? ''}`
    case 'build':
      return `build/${route.buildId ?? ''}`
    case 'build-summaries':
      return 'build-summaries'
    case 'profile-pools':
      return `profile-pools/${route.view}`
  }
}

const PANELS = new Set(['spec', 'specs', 'running', 'changes', 'files', 'terminal', 'terminal-full', 'terminal-remote', 'terminal-docker', 'watch', 'checkpoints', 'trace'])

export function MockApp() {
  const [route, setRoute] = React.useState<MockRoute>(parseHash)
  const [mode, setMode] = React.useState<'dark' | 'light'>(() => (document.documentElement.dataset.mode === 'light' ? 'light' : 'dark'))
  const [collapsed, setCollapsed] = React.useState(() => window.innerWidth < 1000)
  const [before, setBefore] = React.useState(false)

  React.useEffect(() => {
    const onHash = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = React.useCallback((next: MockRoute) => {
    window.location.hash = toHash(next)
    setRoute(next)
  }, [])

  const toggleMode = () => {
    const next = mode === 'dark' ? 'light' : 'dark'
    const root = document.documentElement
    root.classList.add('no-transitions')
    root.dataset.mode = next
    setMode(next)
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('no-transitions')))
  }

  const Screen = screenFor(route)
  const fill = route.kind === 'tab' && (route.tab === 'tasks' || route.tab === 'spec' || route.tab === 'vault')
  const awaitingReview = tasks.filter((t) => t.status === 'under_review' || t.status === 'completed').length
  const beforeSrc = (() => {
    const key = beforeKey(route)
    return key ? BEFORE[`./before/${key}.webp`] : undefined
  })()

  const setupFor = useSetupTitles()
  const buildsNeedingYou = useBuildsNeedingYou()
  const projectBody = useSidebarProjectBody({
    openThread: (agent, conversationId) => go({ kind: 'conversation', agent, conversationId }),
    newThread: () => go({ kind: 'conversation', agent: 'Architect', conversationId: null }),
    openBuild: (buildId) => go({ kind: 'build', buildId }),
    activeConversation: route.kind === 'conversation' ? route.conversationId : null,
    activeBuild: route.kind === 'build' ? route.buildId : null,
  })

  return (
    <div className="aw-app">
      <Sidebar
        activeConversation={route.kind === 'conversation' ? route.conversationId : null}
        compact={collapsed}
        onCompactChange={setCollapsed}
        onOpenProject={() => go({ kind: 'tab', tab: 'overview' })}
        setupFor={setupFor}
        onOpenConversation={(_, agent, conversationId) => go({ kind: 'conversation', agent, conversationId })}
        onNewConversation={(_, agent) => (agent ? go({ kind: 'conversation', agent, conversationId: null }) : undefined)}
        onOpenEnvironment={() => go({ kind: 'settings', section: 'general' })}
        onAddAgent={() => undefined}
        onAddProject={() => undefined}
        onOpenAppSettings={() => go({ kind: 'app-settings', section: 'notifications' })}
        appSettingsActive={route.kind === 'app-settings'}
        projectBody={projectBody}
        buildsNeedingYou={buildsNeedingYou}
      />
      <div className="aw-main">
        <TopBar
          project={{ id: project.id, name: project.name, path: project.working_directory }}
          projects={projects.map((p) => ({ id: p.id, name: p.name, path: p.working_directory }))}
          tabs={LEANER_TABS}
          active={route.kind === 'tab' ? route.tab : route.kind === 'traces' ? 'activity' : route.kind === 'overview-next' ? 'overview' : null}
          // Overview's count is what its "Needs you" section lists (QA1's question and the unmerged task).
          counts={{ tasks: awaitingReview, overview: 2 }}
          onSelectTab={(tab) => go({ kind: 'tab', tab })}
          onSelectProject={() => undefined}
          onOpenPalette={() => undefined}
          onOpenSettings={() => go({ kind: 'settings', section: 'general' })}
          mode={mode}
          onToggleMode={toggleMode}
          settingsActive={route.kind === 'settings'}
        />
        <main className="aw-page" data-fill={fill ? 'true' : 'false'}>
          <React.Suspense fallback={null}>
            <Screen route={route} go={go} now={MOCK_NOW} />
          </React.Suspense>
        </main>
      </div>

      {before && beforeSrc ? (
        <div className="mock-before" onClick={() => setBefore(false)}>
          <img src={beforeSrc} alt="The same screen in today's build" />
          <span className="mock-before-label">Today's build. Click anywhere to return to the mock.</span>
        </div>
      ) : null}

      <MockBar route={route} go={go} before={before} hasBefore={Boolean(beforeSrc)} onBefore={() => setBefore((b) => !b)} />
      <Toaster />
    </div>
  )
}

function MockBar({
  route,
  go,
  before,
  hasBefore,
  onBefore,
}: {
  route: MockRoute
  go: (r: MockRoute) => void
  before: boolean
  hasBefore: boolean
  onBefore: () => void
}) {
  const current = SCREENS.find((s) => toHash(s.route) === toHash(route))?.id ?? ''
  return (
    <div className="mock-bar" role="toolbar" aria-label="Mock controls">
      <span className="mock-bar-tag">Mock</span>
      <select
        className="mock-bar-select"
        aria-label="Screen"
        value={current}
        onChange={(e) => {
          const s = SCREENS.find((x) => x.id === e.target.value)
          if (s) go(s.route)
        }}
      >
        {current === '' ? <option value="">(other)</option> : null}
        {SCREENS.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </select>
      {(route.kind === 'tab' && route.tab === 'spec') || (route.kind === 'conversation' && (route.panel === 'spec' || route.panel === 'specs')) ? (
        <SpecMockBar showLayout={route.kind === 'tab'} />
      ) : null}
      <SidebarMockBar />
      {route.kind === 'tab' && route.tab === 'tasks' ? <TasksMockBar /> : null}
      {route.kind === 'tab' && route.tab === 'profiles' ? <ProfilesMockBar /> : null}
      {route.kind === 'build' || route.kind === 'build-summaries' ? <BuildMockBar showBuild={route.kind === 'build'} /> : null}
      <button type="button" className="mock-bar-button" disabled={!hasBefore} data-on={before ? 'true' : 'false'} onClick={onBefore}>
        {before ? 'Showing today' : 'Compare with today'}
      </button>
    </div>
  )
}

/** The sidebar's states (profiles-threads-and-builds-everywhere), on every screen: the sidebar is. */
function SidebarMockBar() {
  const { state } = useSidebarMock()
  return (
    <select className="mock-bar-select" aria-label="Sidebar" value={state} onChange={(e) => setSidebarMockState(e.target.value as SidebarMockState)}>
      {SIDEBAR_MOCK_STATES.map((s) => (
        <option key={s.value} value={s.value}>
          {s.label}
        </option>
      ))}
    </select>
  )
}

/** The Profiles page's states: the roster, one profile, none, a filter that matches none, a failed
 *  load and a slow one. */
function ProfilesMockBar() {
  const { state, set } = useProfilesAddress()
  return (
    <select className="mock-bar-select" aria-label="Profiles state" value={state} onChange={(e) => set({ state: e.target.value as ProfilesMockState, q: null })}>
      {PROFILES_MOCK_STATES.map((s) => (
        <option key={s.value} value={s.value}>
          {s.label}
        </option>
      ))}
    </select>
  )
}

/** The build view's controls: which recorded build, and the states the recording lacks. */
function BuildMockBar({ showBuild }: { showBuild: boolean }) {
  const { buildId, state, setState } = useBuildHash()
  return (
    <>
      {showBuild ? (
        <select
          className="mock-bar-select"
          aria-label="Build"
          value={buildId ?? DEFAULT_BUILD}
          onChange={(e) => {
            window.location.hash = `build/${e.target.value}${state === 'recorded' ? '' : `?state=${state}`}`
          }}
        >
          {RECORDED_BUILDS.map((b) => (
            <option key={b.build.id} value={b.build.id}>
              {b.build.document_title}
            </option>
          ))}
        </select>
      ) : null}
      <select className="mock-bar-select" aria-label="Build state" value={state} onChange={(e) => setState(e.target.value as BuildMockState)}>
        {BUILD_MOCK_STATES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
    </>
  )
}

/** The Tasks screen's controls: the Dependencies view as a map or as today's list, and a wider
 *  build than the recorded ones. */
function TasksMockBar() {
  const { wide } = useTasksMockControls()
  return (
    <>
      <button type="button" className="mock-bar-button" onClick={() => setTasksMockControls({ wide: !wide })}>
        {wide ? 'Wide build: shown' : 'Wide build: hidden'}
      </button>
    </>
  )
}

/** The spec page's controls: which of the five document states to show, and (open question 2)
 *  whether the document list is a left column or a switcher above a full-width document. */
function SpecMockBar({ showLayout }: { showLayout: boolean }) {
  const { state, layout, notices } = useSpecMockControls()
  return (
    <>
      <select className="mock-bar-select" aria-label="Messages" value={notices} onChange={(e) => setSpecMockControls({ notices: e.target.value as never })}>
        {NOTICE_LEVELS.map((n) => (
          <option key={n.value} value={n.value}>
            {n.label}
          </option>
        ))}
      </select>
      <select className="mock-bar-select" aria-label="Document state" value={state} onChange={(e) => setSpecMockControls({ state: e.target.value as never })}>
        {SPEC_MOCK_STATES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
      {showLayout ? (
        <button type="button" className="mock-bar-button" data-on={layout === 'switcher' ? 'true' : 'false'} onClick={() => setSpecMockControls({ layout: layout === 'column' ? 'switcher' : 'column' })}>
          {layout === 'column' ? 'List: left column' : 'List: top switcher'}
        </button>
      ) : null}
    </>
  )
}

