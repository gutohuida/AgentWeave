import { useState } from 'react'
import { Settings } from 'lucide-react'
import { useConfigStore, type ThemeId } from '@/store/configStore'

interface SetupModalProps {
  open: boolean
  onClose: () => void
}

const THEMES: { id: ThemeId; label: string; bg: string; accent: string }[] = [
  { id: 'ocean',  label: 'Ocean Deep',    bg: '#00121f', accent: '#06b6d4' },
  { id: 'cosmic', label: 'Cosmic Purple', bg: '#0a0018', accent: '#8b5cf6' },
  { id: 'solar',  label: 'Solar Flare',   bg: '#100500', accent: '#fb923c' },
  { id: 'forest', label: 'Forest Night',  bg: '#010f07', accent: '#10b981' },
  { id: 'rose',   label: 'Neon Rose',     bg: '#120008', accent: '#ec4899' },
]

export function SetupModal({ open, onClose }: SetupModalProps) {
  const { hubUrl, apiKey, projectId, theme, setConfig, setTheme } = useConfigStore()
  const [url, setUrl] = useState(hubUrl || 'http://localhost:8000')
  const [key, setKey] = useState(apiKey || '')
  const [proj, setProj] = useState(projectId || 'proj-default')
  const [selectedTheme, setSelectedTheme] = useState<ThemeId>(theme)

  if (!open) return null

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setConfig(key.trim(), url.trim(), proj.trim())
    if (selectedTheme !== theme) setTheme(selectedTheme)
    onClose()
  }

  function handleThemePreview(id: ThemeId) {
    setSelectedTheme(id)
    document.documentElement.dataset.theme = id
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl p-6 glass" style={{ boxShadow: '0 25px 60px rgba(0,0,0,0.5)' }}>
        <div className="mb-5 flex items-center gap-2">
          <Settings className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold text-white">Connect to AgentWeave Hub</h2>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-white/50 uppercase tracking-wider">Hub URL</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full rounded-xl px-3 py-2 text-sm text-white/90 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-primary"
              style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)' }}
              placeholder="http://localhost:8000"
              required
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-white/50 uppercase tracking-wider">API Key</label>
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="w-full rounded-xl px-3 py-2 text-sm text-white/90 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-primary"
              style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)' }}
              placeholder="aw_live_..."
              required
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-white/50 uppercase tracking-wider">Project ID</label>
            <input
              type="text"
              value={proj}
              onChange={(e) => setProj(e.target.value)}
              className="w-full rounded-xl px-3 py-2 text-sm text-white/90 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-primary"
              style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)' }}
              placeholder="proj-default"
            />
          </div>

          {/* Theme picker */}
          <div>
            <label className="mb-2 block text-xs font-medium text-white/50 uppercase tracking-wider">Color Theme</label>
            <div className="flex gap-2">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  title={t.label}
                  onClick={() => handleThemePreview(t.id)}
                  className={`relative flex-1 rounded-xl overflow-hidden transition-all ${
                    selectedTheme === t.id ? 'ring-2 ring-white/60 scale-105' : 'ring-1 ring-white/10 hover:ring-white/25'
                  }`}
                  style={{ background: t.bg, height: 48 }}
                >
                  <span className="absolute inset-0 opacity-50"
                        style={{ background: `radial-gradient(ellipse at 50% 0%, ${t.accent}66 0%, transparent 70%)` }} />
                  <span className="absolute bottom-1.5 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full"
                        style={{ background: t.accent }} />
                  {selectedTheme === t.id && (
                    <span className="absolute top-1 right-1 w-3.5 h-3.5 rounded-full bg-white/90 flex items-center justify-center">
                      <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                        <path d="M1 4l2 2 4-4" stroke="#000" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </span>
                  )}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-white/30">
              {THEMES.find(t => t.id === selectedTheme)?.label}
            </p>
          </div>

          <button
            type="submit"
            className="w-full rounded-xl py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 focus:outline-none focus:ring-1 focus:ring-primary"
            style={{ background: 'linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary) / 0.7))' }}
          >
            Connect
          </button>
        </form>
      </div>
    </div>
  )
}
