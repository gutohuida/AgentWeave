import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/index.css'
import '@/styles/primitives.css'
import './mock.css'
import './loom.css'
import { Segmented } from '@/components/ui/segmented'
import type { LoomOrientation, LoomStyle } from '@/components/thread/loom/Loom'
import ThreadLoomScreen from './screens/ThreadLoom'

// The Thread page redrawn as a loom, for the operator to judge (2026-10-24). Fed only by
// mock/thread-chapters-fixture.json.   npx vite --config vite.mock.config.ts
//   -> http://localhost:5199/mock-loom.html?mode=dark&layout=horizontal&thread=wave
const params = new URLSearchParams(window.location.search)
const now = new Date('2026-10-24T23:00:00Z')

// eslint-disable-next-line react-refresh/only-export-components -- a mock entry point, not a module
function Page() {
  const [dark, setDark] = React.useState(params.get('mode') !== 'light')
  const [orientation, setOrientation] = React.useState<LoomOrientation>(params.get('layout') === 'vertical' ? 'vertical' : 'horizontal')
  const [threadStyle, setThreadStyle] = React.useState<LoomStyle>(params.get('thread') === 'rope' ? 'rope' : 'wave')
  const [drawKey, setDrawKey] = React.useState(0)
  React.useEffect(() => {
    document.documentElement.dataset.mode = dark ? 'dark' : 'light'
  }, [dark])
  return (
    <main className="aw-page" style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="mock-loom-bar">
        <span className="mock-loom-bar-name">Thread mock</span>
        <Segmented
          label="Layout"
          value={orientation}
          onChange={setOrientation}
          options={[
            { value: 'horizontal', label: 'Left to right' },
            { value: 'vertical', label: 'Top to bottom' },
          ]}
        />
        <Segmented
          label="Thread"
          value={threadStyle}
          onChange={setThreadStyle}
          options={[
            { value: 'wave', label: 'Wave' },
            { value: 'rope', label: 'Rope' },
          ]}
        />
        <Segmented
          label="Mode"
          value={dark ? 'dark' : 'light'}
          onChange={(v) => setDark(v === 'dark')}
          options={[
            { value: 'dark', label: 'Dark' },
            { value: 'light', label: 'Light' },
          ]}
        />
        <button type="button" data-slot="mock-replay" className="mock-loom-replay" onClick={() => setDrawKey((n) => n + 1)}>
          Replay
        </button>
      </div>
      <ThreadLoomScreen orientation={orientation} threadStyle={threadStyle} drawKey={drawKey} now={now} />
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Page />
  </React.StrictMode>,
)
