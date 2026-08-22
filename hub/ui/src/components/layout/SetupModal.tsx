import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useConfigStore, type ModeId } from '@/store/configStore'

interface SetupModalProps {
  open: boolean
  onClose: () => void
}

export function SetupModal({ open, onClose }: SetupModalProps) {
  const { hubUrl, apiKey, selectedProjectId, mode, setConfig, setSelectedProject, setMode } =
    useConfigStore()
  const [url,          setUrl]          = useState(hubUrl || 'http://localhost:8000')
  const [key,          setKey]          = useState(apiKey || '')
  const [proj,         setProj]         = useState(selectedProjectId || '')
  const [selectedMode, setSelectedMode] = useState<ModeId>(mode)
  const urlInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) urlInput.current?.focus()
  }, [open])

  if (!open) return null

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setConfig(key.trim(), url.trim())
    if (proj.trim()) setSelectedProject(proj.trim())
    if (selectedMode !== mode) {
      setMode(selectedMode)
      document.documentElement.dataset.mode = selectedMode
    }
    onClose()
  }

  function handleModePreview(m: ModeId) {
    setSelectedMode(m)
    document.documentElement.dataset.mode = m
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'var(--scrim)' }}
    >
      <div
        className="setup-dialog elevation-overlay w-full max-w-md p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="setup-title"
        aria-describedby="setup-description"
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--radius-lg)',
        }}
      >
        {/* Header */}
        <div className="mb-5 flex items-center gap-3">
          <Icon name="settings" size={22} style={{ color: 'var(--blue)' }} />
          <div>
          <h2 id="setup-title" className="text-lg font-semibold" style={{ color: 'var(--text)' }}>
            Connect to AgentWeave Hub
          </h2>
          <p id="setup-description" className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>Use the credentials and optional project context for this Hub instance.</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Hub URL */}
          <div>
            <label htmlFor="setup-hub-url" className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>
              Hub URL
            </label>
            <input
              ref={urlInput}
              id="setup-hub-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="control-field px-3 py-2 text-[13px]"
              placeholder="http://localhost:8000"
              required
            />
          </div>

          {/* API Key */}
          <div>
            <label htmlFor="setup-api-key" className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>
              API Key
            </label>
            <input
              id="setup-api-key"
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="control-field px-3 py-2 text-[13px]"
              placeholder="aw_live_..."
              required
            />
          </div>

          {/* Project ID — optional manual override; normally auto-selected
              from the instance's project collection on bootstrap. */}
          <div>
            <label htmlFor="setup-project-id" className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>
              Project ID (optional)
            </label>
            <input
              id="setup-project-id"
              type="text"
              value={proj}
              onChange={(e) => setProj(e.target.value)}
              className="control-field px-3 py-2 text-[13px]"
              placeholder="auto-selected"
            />
          </div>

          {/* Mode selector — light/dark is the only appearance choice; the palette
              itself is fixed (2026-08-04-hub-charcoal-visual-refresh). */}
          <div>
            <label className="mb-2 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>Mode</label>
            <div className="flex gap-2">
              {(['light', 'dark'] as ModeId[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={selectedMode === m}
                  onClick={() => handleModePreview(m)}
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl py-2.5 text-[13px] font-medium transition-all"
                  style={{
                    background: m === 'light' ? '#ffffff' : '#0a0a0b',
                    color:      m === 'light' ? '#18181b' : '#f5f5f6',
                    outline:    selectedMode === m ? '2px solid var(--ring)' : '1px solid var(--border)',
                    outlineOffset: '2px',
                  }}
                >
                  <Icon
                    name={m === 'light' ? 'light_mode' : 'dark_mode'}
                    size={18}
                    style={{ color: m === 'light' ? '#18181b' : '#f5f5f6' }}
                  />
                  {m === 'light' ? 'Light' : 'Dark'}
                </button>
              ))}
            </div>
          </div>

          <Button type="submit" variant="primary" size="md" className="w-full">
            Connect
          </Button>
        </form>
      </div>
    </div>
  )
}
