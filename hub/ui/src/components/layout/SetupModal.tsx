import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useConfigStore, type ThemeId, type ModeId } from '@/store/configStore'

interface SetupModalProps {
  open: boolean
  onClose: () => void
}

const THEMES: { id: ThemeId; label: string; primary: string; bg: string; bgDark: string }[] = [
  { id: 'cosmic', label: 'Purple', primary: '#6750a4', bg: '#fffbfe', bgDark: '#1c1b1f' },
  { id: 'ocean',  label: 'Blue',   primary: '#0061a4', bg: '#fafcff', bgDark: '#001d36' },
  { id: 'forest', label: 'Green',  primary: '#006e21', bg: '#f7fdf7', bgDark: '#002106' },
  { id: 'solar',  label: 'Orange', primary: '#9c4100', bg: '#fffbff', bgDark: '#201a18' },
  { id: 'rose',   label: 'Rose',   primary: '#984061', bg: '#fffbff', bgDark: '#201318' },
]

export function SetupModal({ open, onClose }: SetupModalProps) {
  const { hubUrl, apiKey, projectId, theme, mode, setConfig, setTheme, setMode } = useConfigStore()
  const [url,           setUrl]           = useState(hubUrl || 'http://localhost:8000')
  const [key,           setKey]           = useState(apiKey || '')
  const [proj,          setProj]          = useState(projectId || 'proj-default')
  const [selectedTheme, setSelectedTheme] = useState<ThemeId>(theme)
  const [selectedMode,  setSelectedMode]  = useState<ModeId>(mode)

  if (!open) return null

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setConfig(key.trim(), url.trim(), proj.trim())
    if (selectedTheme !== theme) {
      setTheme(selectedTheme)
      document.documentElement.dataset.theme = selectedTheme
    }
    if (selectedMode !== mode) {
      setMode(selectedMode)
      document.documentElement.dataset.mode = selectedMode
    }
    onClose()
  }

  function handleThemePreview(id: ThemeId) {
    setSelectedTheme(id)
    document.documentElement.dataset.theme = id
  }

  function handleModePreview(m: ModeId) {
    setSelectedMode(m)
    document.documentElement.dataset.mode = m
  }

  const currentBg = selectedMode === 'dark'
    ? (THEMES.find(t => t.id === selectedTheme)?.bgDark ?? '#09090b')
    : (THEMES.find(t => t.id === selectedTheme)?.bg ?? '#ffffff')

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

          {/* Project ID */}
          <div>
            <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>
              Project ID
            </label>
            <input
              type="text"
              value={proj}
              onChange={(e) => setProj(e.target.value)}
              style={inputStyle}
              placeholder="proj-default"
            />
          </div>

          {/* Mode selector */}
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
                    background: m === 'light' ? '#ffffff' : '#09090b',
                    color:      m === 'light' ? '#18181b' : '#fafafa',
                    outline:    selectedMode === m ? '2px solid var(--blue)' : '1px solid var(--border)',
                    outlineOffset: '2px',
                  }}
                >
                  <Icon
                    name={m === 'light' ? 'light_mode' : 'dark_mode'}
                    size={18}
                    style={{ color: m === 'light' ? '#18181b' : '#fafafa' }}
                  />
                  {m === 'light' ? 'Light' : 'Dark'}
                </button>
              ))}
            </div>
          </div>

          {/* Theme palette picker */}
          <div>
            <label className="mb-2 block text-xs font-medium" style={{ color: 'var(--text-3)' }}>Color Palette</label>
            <div className="flex gap-2">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  title={t.label}
                  onClick={() => handleThemePreview(t.id)}
                  className="relative flex-1 rounded-xl overflow-hidden transition-all"
                  style={{
                    background:    currentBg,
                    height:        52,
                    outline:       selectedTheme === t.id ? '2px solid var(--blue)' : '1px solid var(--border)',
                    outlineOffset: '2px',
                    transform:     selectedTheme === t.id ? 'scale(1.05)' : 'scale(1)',
                  }}
                >
                  {/* Color dot */}
                  <span
                    className="absolute bottom-2 left-1/2 -translate-x-1/2 w-5 h-5 rounded-full"
                    style={{ background: t.primary }}
                  />
                  {/* Label */}
                  <span
                    className="absolute top-1.5 left-1/2 -translate-x-1/2 text-[11px] whitespace-nowrap"
                    style={{ color: selectedMode === 'dark' ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.5)' }}
                  >
                    {t.label}
                  </span>
                  {/* Checkmark */}
                  {selectedTheme === t.id && (
                    <span
                      className="absolute top-1 right-1 w-4 h-4 rounded-full flex items-center justify-center"
                      style={{ background: 'var(--blue)' }}
                    >
                      <Icon name="check" size={11} style={{ color: '#fff' }} />
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          <button
            type="submit"
            className="w-full"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              height: 40,
              borderRadius: 'var(--radius)',
              padding: '0 24px',
              background: 'var(--blue)',
              color: '#fff',
              border: 'none',
              fontSize: 14,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Connect
          </button>
        </form>
      </div>
    </div>
  )
}
