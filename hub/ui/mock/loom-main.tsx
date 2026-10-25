import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/index.css'
import '@/styles/primitives.css'
import './mock.css'
import './loom.css'
import { Segmented } from '@/components/ui/segmented'
import ThreadLoomScreen from './screens/ThreadLoom'

// The Thread page as a loom, approved by the operator as rendered (2026-10-24/25): left to right, a
// single wave. Fed only by mock/thread-chapters-fixture.json.   npx vite --config vite.mock.config.ts
//   -> http://localhost:5199/mock-loom.html?mode=dark  (the old layout/thread switches are retired)
const params = new URLSearchParams(window.location.search)
const now = new Date('2026-10-24T23:00:00Z')

// eslint-disable-next-line react-refresh/only-export-components -- a mock entry point, not a module
function Page() {
  const [dark, setDark] = React.useState(params.get('mode') !== 'light')
  const [drawKey, setDrawKey] = React.useState(0)
  React.useEffect(() => {
    document.documentElement.dataset.mode = dark ? 'dark' : 'light'
  }, [dark])
  return (
    <main className="aw-page" style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="mock-loom-bar">
        <span className="mock-loom-bar-name">Thread mock</span>
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
      <ThreadLoomScreen drawKey={drawKey} now={now} />
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Page />
  </React.StrictMode>,
)
