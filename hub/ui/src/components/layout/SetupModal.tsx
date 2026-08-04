import { useState } from 'react'
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

  const inputStyle: React.CSSProperties = {
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text)',
    padding: '8px 12px',
    width: '100%',
    fontSize: 13,
    outline: 'none',
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm"
      style={{ background: 'var(--scrim)' }}
    >
      <div
        className="w-full max-w-md p-6"
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border)',
        }}
      >
        {/* Header */}
        <div className="mb-5 flex items-center gap-3">
          <Icon name="settings" size={22} style={{ color: 'var(--blue)' }} />
          <h2 className="text-lg font-normal" style={{ color: 'var(--text)' }}>
            Connect to AgentWeave Hub
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Hub URL */}
          <div>
            <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>
              Hub URL
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              style={inputStyle}
              placeholder="http://localhost:8000"
              required
            />
          </div>

          {/* API Key */}
          <div>
            <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>
              API Key
            </label>
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              style={inputStyle}
              placeholder="aw_live_..."
              required
            />
          </div>

          {/* Project ID — optional manual override; normally auto-selected
              from the instance's project collection on bootstrap. */}
          <div>
            <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>
              Project ID (optional)
            </label>
            <input
              type="text"
              value={proj}
              onChange={(e) => setProj(e.target.value)}
              style={inputStyle}
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
