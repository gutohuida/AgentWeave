import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/index.css'
import '@/styles/primitives.css'
import './mock.css'
import ThreadScreen from './screens/Thread'

// The Thread page on its own, fed only by mock/thread-fixture.json: it needs none of the replica
// fixtures the full mock reads, so any checkout can render it. Mode: ?mode=light|dark.
//   npx vite --config vite.mock.config.ts   ->   http://localhost:5199/mock-thread.html
const mode = new URLSearchParams(window.location.search).get('mode') === 'light' ? 'light' : 'dark'
document.documentElement.dataset.mode = mode
const now = new Date('2026-10-23T20:00:00Z')

// eslint-disable-next-line react-refresh/only-export-components -- a mock entry point, not a module
function Page() {
  const [dark, setDark] = React.useState(mode === 'dark')
  React.useEffect(() => {
    document.documentElement.dataset.mode = dark ? 'dark' : 'light'
  }, [dark])
  return (
    <main className="aw-page" style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
      <ThreadScreen route={{ kind: 'thread' }} go={() => undefined} now={now} />
      <button
        type="button"
        data-slot="mock-mode"
        onClick={() => setDark((d) => !d)}
        style={{ position: 'fixed', right: 16, top: 12, zIndex: 5, padding: '4px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-2)', fontSize: 12 }}
      >
        {dark ? 'Light' : 'Dark'}
      </button>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Page />
  </React.StrictMode>,
)
