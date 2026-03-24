import { useState } from 'react'
import { Icon } from '@/components/common/Icon'

interface AddAgentDialogProps {
  isOpen: boolean
  onClose: () => void
  onAdd: (agentName: string, role: string, yoloEnabled: boolean) => Promise<void>
  existingAgents: string[]
}

const COMMON_AGENTS = [
  { name: 'claude', label: 'Claude', description: 'Anthropic Claude Code' },
  { name: 'kimi', label: 'Kimi', description: 'Moonshot AI Kimi Code' },
  { name: 'gemini', label: 'Gemini', description: 'Google Gemini CLI' },
  { name: 'codex', label: 'Codex', description: 'OpenAI Codex CLI' },
  { name: 'opencode', label: 'OpenCode', description: 'OpenCode multi-model CLI' },
]

export function AddAgentDialog({
  isOpen,
  onClose,
  onAdd,
  existingAgents,
}: AddAgentDialogProps) {
  const [step, setStep] = useState<'select' | 'configure'>('select')
  const [selectedAgent, setSelectedAgent] = useState('')
  const [customName, setCustomName] = useState('')
  const [role, setRole] = useState('delegate')
  const [yoloEnabled, setYoloEnabled] = useState(false)
  const [isAdding, setIsAdding] = useState(false)
  const [error, setError] = useState('')

  if (!isOpen) return null

  const existingSet = new Set(existingAgents.map((a) => a.toLowerCase()))
  const availableAgents = COMMON_AGENTS.filter((a) => !existingSet.has(a.name))

  const handleSelectAgent = (agentName: string) => {
    setSelectedAgent(agentName)
    setStep('configure')
    setError('')
  }

  const handleSelectCustom = () => {
    const name = customName.trim().toLowerCase()
    if (!name) {
      setError('Please enter an agent name')
      return
    }
    if (existingSet.has(name)) {
      setError('Agent already exists')
      return
    }
    setSelectedAgent(name)
    setStep('configure')
    setError('')
  }

  const handleAdd = async () => {
    setIsAdding(true)
    setError('')
    try {
      await onAdd(selectedAgent, role, yoloEnabled)
      resetForm()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add agent')
    } finally {
      setIsAdding(false)
    }
  }

  const resetForm = () => {
    setStep('select')
    setSelectedAgent('')
    setCustomName('')
    setRole('delegate')
    setYoloEnabled(false)
    setError('')
  }

  const handleClose = () => {
    resetForm()
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div
        className="w-full max-w-lg rounded-2xl shadow-xl overflow-hidden"
        style={{ background: 'var(--surface-low)', maxHeight: '90vh' }}
      >
        {/* Header */}
        <div
          className="p-4 border-b flex items-center justify-between"
          style={{ borderColor: 'var(--outline-variant)' }}
        >
          <h2 className="m3-title-large" style={{ color: 'var(--on-sv)' }}>
            {step === 'select' ? 'Add Agent' : 'Configure Agent'}
          </h2>
          <button onClick={handleClose} className="m3-icon-btn">
            <Icon name="close" size={24} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto" style={{ maxHeight: 'calc(90vh - 140px)' }}>
          {step === 'select' ? (
            <div className="space-y-4">
              {/* Common Agents */}
              {availableAgents.length > 0 && (
                <div>
                  <label
                    className="m3-label-large block mb-2"
                    style={{ color: 'var(--on-sv)' }}
                  >
                    Popular Agents
                  </label>
                  <div className="grid grid-cols-1 gap-2">
                    {availableAgents.map((agent) => (
                      <button
                        key={agent.name}
                        onClick={() => handleSelectAgent(agent.name)}
                        className="p-3 rounded-lg text-left flex items-center gap-3 transition-colors"
                        style={{
                          background: 'var(--surface-high)',
                        }}
                        onMouseEnter={(e) =>
                          ((e.currentTarget as HTMLElement).style.background =
                            'var(--surface-highest)')
                        }
                        onMouseLeave={(e) =>
                          ((e.currentTarget as HTMLElement).style.background =
                            'var(--surface-high)')
                        }
                      >
                        <div
                          className="w-10 h-10 rounded-full flex items-center justify-center"
                          style={{ background: 'var(--p-cont)' }}
                        >
                          <Icon name="smart_toy" size={20} style={{ color: 'var(--primary)' }} />
                        </div>
                        <div className="flex-1">
                          <div
                            className="m3-body-large font-medium"
                            style={{ color: 'var(--on-sv)' }}
                          >
                            {agent.label}
                          </div>
                          <div
                            className="m3-body-small opacity-70"
                            style={{ color: 'var(--on-sv)' }}
                          >
                            {agent.description}
                          </div>
                        </div>
                        <Icon name="chevron_right" size={20} style={{ color: 'var(--on-sv)' }} />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Custom Agent */}
              <div>
                <label
                  className="m3-label-large block mb-2"
                  style={{ color: 'var(--on-sv)' }}
                >
                  Custom Agent
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    placeholder="e.g., my-custom-agent"
                    className="flex-1 px-3 py-2 rounded-lg m3-body-medium"
                    style={{
                      background: 'var(--surface-high)',
                      color: 'var(--on-sv)',
                      border: '1px solid var(--outline-variant)',
                    }}
                    onKeyDown={(e) => e.key === 'Enter' && handleSelectCustom()}
                  />
                  <button
                    onClick={handleSelectCustom}
                    disabled={!customName.trim()}
                    className="m3-btn-filled"
                  >
                    Next
                  </button>
                </div>
              </div>

              {error && (
                <div
                  className="p-3 rounded-lg m3-body-medium"
                  style={{ background: 'var(--error-cont)', color: 'var(--on-error-cont)' }}
                >
                  <Icon name="error" size={18} className="inline mr-1" />
                  {error}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {/* Selected Agent Header */}
              <div
                className="p-4 rounded-xl flex items-center gap-3"
                style={{ background: 'var(--p-cont)' }}
              >
                <Icon name="smart_toy" size={28} style={{ color: 'var(--primary)' }} />
                <div>
                  <div
                    className="m3-body-large font-medium capitalize"
                    style={{ color: 'var(--on-p-cont)' }}
                  >
                    {selectedAgent}
                  </div>
                  <button
                    onClick={() => setStep('select')}
                    className="m3-label-small opacity-70"
                    style={{ color: 'var(--on-p-cont)' }}
                  >
                    Change agent
                  </button>
                </div>
              </div>

              {/* Role Selection */}
              <div>
                <label
                  className="m3-label-large block mb-2"
                  style={{ color: 'var(--on-sv)' }}
                >
                  Role
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(['principal', 'delegate', 'reviewer'] as const).map((r) => (
                    <button
                      key={r}
                      onClick={() => setRole(r)}
                      className="p-3 rounded-lg border-2 text-center transition-all"
                      style={{
                        background: role === r ? 'var(--p-cont)' : 'var(--surface-high)',
                        borderColor: role === r ? 'var(--primary)' : 'transparent',
                      }}
                    >
                      <span
                        className="m3-label-large block capitalize"
                        style={{ color: role === r ? 'var(--on-p-cont)' : 'var(--on-sv)' }}
                      >
                        {r}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* YOLO Toggle */}
              <div
                className="p-4 rounded-xl border flex items-center justify-between"
                style={{
                  borderColor: yoloEnabled ? 'var(--destructive)' : 'var(--outline-variant)',
                  background: yoloEnabled ? 'var(--error-cont)' : 'var(--surface-high)',
                }}
              >
                <div className="flex items-center gap-3">
                  <span className="text-2xl">🚀</span>
                  <div>
                    <div
                      className="m3-label-large"
                      style={{
                        color: yoloEnabled ? 'var(--on-error-cont)' : 'var(--on-sv)',
                      }}
                    >
                      YOLO Mode
                    </div>
                    <div
                      className="m3-body-small opacity-70"
                      style={{
                        color: yoloEnabled ? 'var(--on-error-cont)' : 'var(--on-sv)',
                      }}
                    >
                      Auto-approve all tool calls
                    </div>
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={yoloEnabled}
                    onChange={(e) => setYoloEnabled(e.target.checked)}
                    className="sr-only"
                  />
                  <div
                    className="w-14 h-7 rounded-full transition-colors relative"
                    style={{
                      background: yoloEnabled ? 'var(--destructive)' : 'var(--surface-highest)',
                    }}
                  >
                    <div
                      className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full transition-transform ${
                        yoloEnabled ? 'translate-x-7' : 'translate-x-0'
                      }`}
                    />
                  </div>
                </label>
              </div>

              {yoloEnabled && (
                <div
                  className="p-3 rounded-lg text-sm"
                  style={{
                    background: 'var(--destructive)',
                    color: 'var(--destructive-fg)',
                  }}
                >
                  <Icon name="warning" size={16} className="inline mr-1" />
                  <strong>Warning:</strong> YOLO mode gives the agent full autonomy. Use with
                  caution!
                </div>
              )}

              {error && (
                <div
                  className="p-3 rounded-lg m3-body-medium"
                  style={{ background: 'var(--error-cont)', color: 'var(--on-error-cont)' }}
                >
                  <Icon name="error" size={18} className="inline mr-1" />
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="p-4 border-t flex justify-end gap-2"
          style={{ borderColor: 'var(--outline-variant)' }}
        >
          <button onClick={handleClose} className="m3-btn-text">
            Cancel
          </button>
          {step === 'configure' && (
            <button
              onClick={handleAdd}
              disabled={isAdding}
              className="m3-btn-filled"
            >
              {isAdding ? (
                <>
                  <Icon name="progress_activity" size={20} className="animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <Icon name="add" size={20} />
                  Add Agent
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
