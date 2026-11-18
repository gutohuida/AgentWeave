// Mounts the real Composer with fixture props. The drive reads `window.__sent` for submitted text,
// and `window.__touch(id)` marks a document updated now, as an edit to it would.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Composer } from '@/components/agents/Composer'
import '@/index.css'
import type { SpecReferenceTarget } from '@/lib/composerTriggerSources'

declare global {
  interface Window {
    __sent: string[]
    __touch: (id: string) => void
  }
}
window.__sent = []

const doc = (n: number, title: string, updated: string): SpecReferenceTarget => ({
  id: `spdoc-00000000000${n.toString(16)}`,
  title,
  path: `spec/changes/doc-${n}/spec.json`,
  updated_at: updated,
})

// The project's documents in the order the documents route returns them: insertion order, oldest
// row first, not by update time (hub/hub/spec_lifecycle.py list_documents has no ORDER BY).
// A, B and C all contain 'ref'; by update time C is newest, then A, then B. Twelve documents, so
// the Specs group's cap of 10 is reached by `@` alone.
const SPECS: SpecReferenceTarget[] = [
  doc(1, 'SPEC-1', '2026-11-18T12:00:00Z'),
  doc(2, 'Ref A: reference boxes', '2026-11-17T10:00:00Z'),
  doc(3, 'Ref B: older reference', '2026-11-10T10:00:00Z'),
  doc(4, 'The spec header, redesigned', '2026-11-12T09:00:00Z'),
  doc(5, 'Ref C: newest reference', '2026-11-18T11:00:00Z'),
  doc(6, 'Loop queue ownership', '2026-11-01T09:00:00Z'),
  doc(7, 'Knowledge vault manager', '2026-11-02T09:00:00Z'),
  doc(8, 'Dashboards', '2026-11-03T09:00:00Z'),
  doc(9, 'Flow distribution', '2026-11-04T09:00:00Z'),
  doc(10, 'Brand identity', '2026-11-05T09:00:00Z'),
  doc(11, 'Model record', '2026-11-06T09:00:00Z'),
  doc(12, 'Thread chapters', '2026-11-07T09:00:00Z'),
]

function Harness() {
  const [specs, setSpecs] = useState(SPECS)
  useEffect(() => {
    window.__touch = (id) =>
      setSpecs((all) => all.map((s) => (s.id === id ? { ...s, updated_at: new Date().toISOString() } : s)))
  }, [])
  return (
    <Composer
      agent="alpha"
      projectId="proj-harness"
      conversationId="conv-harness"
      isRunning={false}
      workspacePaths={['README.md', 'hub/ui/src/components/spec/SpecDocumentHeader.tsx', 'hub/ui/src/main.tsx', 'docs/headless.md']}
      specDocuments={specs}
      onSubmit={async (text) => {
        window.__sent.push(text)
      }}
    />
  )
}

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={client}>
    <Harness />
  </QueryClientProvider>,
)
