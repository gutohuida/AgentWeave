import { useState } from 'react'
import { Settings } from 'lucide-react'
import { useConfigStore } from '@/store/configStore'

interface SetupModalProps {
  open: boolean
  onClose: () => void
}

export function SetupModal({ open, onClose }: SetupModalProps) {
  const { hubUrl, apiKey, projectId, setConfig } = useConfigStore()
  const [url, setUrl] = useState(hubUrl || 'http://localhost:8000')
  const [key, setKey] = useState(apiKey || '')
  const [proj, setProj] = useState(projectId || 'proj-default')

  if (!open) return null

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setConfig(key.trim(), url.trim(), proj.trim())
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border bg-card p-6 shadow-2xl">
        <div className="mb-4 flex items-center gap-2">
          <Settings className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">Connect to AgentWeave Hub</h2>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Hub URL</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="http://localhost:8000"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">API Key</label>
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="aw_live_..."
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Project ID</label>
            <input
              type="text"
              value={proj}
              onChange={(e) => setProj(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="proj-default"
            />
          </div>
          <button
            type="submit"
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring"
          >
            Connect
          </button>
        </form>
      </div>
    </div>
  )
}
