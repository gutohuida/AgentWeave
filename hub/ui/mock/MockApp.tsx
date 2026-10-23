import * as React from 'react'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'
import { Toaster } from '@/components/ui/toast'
import { PROJECT_TABS, type ProjectTab } from '@/lib/navigation'
import { MOCK_NOW, project, projects, tasks } from './fixtures'
import { beforeKey, type MockRoute } from './routes'
import { SCREENS, screenFor } from './screens'

const BEFORE = import.meta.glob('./before/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>

function parseHash(): MockRoute {
  const raw = decodeURIComponent(window.location.hash.replace(/^#/, ''))
  const [kind, a, b] = raw.split('/')
  if (kind === 'tab' && (PROJECT_TABS as readonly string[]).includes(a ?? '')) return { kind: 'tab', tab: a as ProjectTab }
  if (kind === 'conversation' && a) return { kind: 'conversation', agent: a, conversationId: b || null }
  if (kind === 'settings') return { kind: 'settings', section: (a as never) || 'general' }
  if (kind === 'agent-settings' && a) return { kind: 'agent-settings', agent: a, section: (b as never) || 'execution' }
  if (kind === 'gallery') return { kind: 'gallery' }
  if (kind === 'thread') return { kind: 'thread' }
  return { kind: 'tab', tab: 'overview' }
}

function toHash(route: MockRoute): string {
  switch (route.kind) {
    case 'tab':
      return `tab/${route.tab}`
    case 'conversation':
      return `conversation/${route.agent}/${route.conversationId ?? ''}`
    case 'settings':
      return `settings/${route.section}`
    case 'agent-settings':
      return `agent-settings/${route.agent}/${route.section}`
    case 'gallery':
      return 'gallery'
    case 'thread':
      return 'thread'
  }
}

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

  return (
    <div className="aw-app">
      <Sidebar
        activeAgent={route.kind === 'conversation' || route.kind === 'agent-settings' ? route.agent : null}
        activeConversation={route.kind === 'conversation' ? route.conversationId : null}
        compact={collapsed}
        onCompactChange={setCollapsed}
        onOpenProject={() => go({ kind: 'tab', tab: 'overview' })}
        onOpenAgent={(_, agent) => go({ kind: 'conversation', agent, conversationId: null })}
        onOpenConversation={(_, agent, conversationId) => go({ kind: 'conversation', agent, conversationId })}
        onNewConversation={(_, agent) => (agent ? go({ kind: 'conversation', agent, conversationId: null }) : undefined)}
        onOpenEnvironment={() => go({ kind: 'settings', section: 'general' })}
        onOpenAgentSettings={(_, agent) => go({ kind: 'agent-settings', agent, section: 'execution' })}
        onAddAgent={() => undefined}
        onAddProject={() => undefined}
      />
      <div className="aw-main">
        <TopBar
          project={{ id: project.id, name: project.name, path: project.working_directory }}
          projects={projects.map((p) => ({ id: p.id, name: p.name, path: p.working_directory }))}
          tabs={PROJECT_TABS}
          active={route.kind === 'tab' ? route.tab : null}
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
      <button type="button" className="mock-bar-button" disabled={!hasBefore} data-on={before ? 'true' : 'false'} onClick={onBefore}>
        {before ? 'Showing today' : 'Compare with today'}
      </button>
    </div>
  )
}
