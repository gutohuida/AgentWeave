// Mounts the real Composer with fixture props. The drive reads `window.__sent` for submitted text.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRoot } from 'react-dom/client'
import { Composer } from '@/components/agents/Composer'

declare global {
  interface Window {
    __sent: string[]
  }
}
window.__sent = []

// The project's documents as the document list reports them; RSSC-2 feeds these to the @ menu.
export const SPECS = [{ id: 'spdoc-000000000001', title: 'SPEC-1', path: 'spec/changes/spec-1/spec.json', updated_at: '2026-11-18T12:00:00Z' }]

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={client}>
    <Composer
      agent="alpha"
      projectId="proj-harness"
      conversationId="conv-harness"
      isRunning={false}
      workspacePaths={['README.md', 'hub/ui/src/main.tsx']}
      onSubmit={async (text) => {
        window.__sent.push(text)
      }}
    />
  </QueryClientProvider>,
)
