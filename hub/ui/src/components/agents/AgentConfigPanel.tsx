import { useState, useEffect } from 'react'
import { Icon } from '@/components/common/Icon'
import type { AgentConfig, UpdateAgentConfigRequest } from '@/api/agentConfig'

interface AgentConfigPanelProps {
  agent: AgentConfig | null
  onUpdate: (agentName: string, config: UpdateAgentConfigRequest) => Promise<void>
  onRemove: (agentName: string) => Promise<void>
  isLoading?: boolean
}

export function AgentConfigPanel({
  agent,
  onUpdate,
  onRemove,
  isLoading,
}: AgentConfigPanelProps) {
  const [role, setRole] = useState(agent?.role || 'delegate')
  const [yoloEnabled, setYoloEnabled] = useState(agent?.yolo_enabled || false)
  const [hasChanges, setHasChanges] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false)

  // Update local state when agent changes
  useEffect(() => {
    if (agent) {
      setRole(agent.role)
      setYoloEnabled(agent.yolo_enabled)
      setHasChanges(false)
      setShowRemoveConfirm(false)
    }
  }, [agent?.agent])

  // Check for changes
  useEffect(() => {
    if (!agent) return
    const changed = role !== agent.role || yoloEnabled !== agent.yolo_enabled
    setHasChanges(changed)
  }, [role, yoloEnabled, agent])

  const handleSave = async () => {
    if (!agent) return
    setIsSaving(true)
    try {
      await onUpdate(agent.agent, { role, yolo_enabled: yoloEnabled })
      setHasChanges(false)
    } finally {
      setIsSaving(false)
    }
  }

  const handleRemove = async () => {
    if (!agent) return
    await onRemove(agent.agent)
    setShowRemoveConfirm(false)
  }

  if (!agent) {
    return (
      <div
        className="h-full flex flex-col items-center justify-center p-8"
        style={{ background: 'var(--surface-low)' }}
      >
        <Icon name="smart_toy" size={64} className="opacity-20 mb-4" />
        <p className="m3-body-large opacity-50" style={{ color: 'var(--on-sv)' }}>
          Select an agent to configure
        </p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col" style={{ background: 'var(--surface-low)' }}>
      {/* Header */}
      <div
        className="p-6 border-b"
        style={{ borderColor: 'var(--outline-variant)' }}
      >
        <div className="flex items-center gap-4">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center"
            style={{ background: 'var(--p-cont)' }}
          >
            <Icon name="smart_toy" size={32} style={{ color: 'var(--primary)' }} />
          </div>
          <div className="flex-1">
            <h1
              className="m3-headline-small capitalize"
              style={{ color: 'var(--on-sv)' }}
            >
              {agent.agent}
            </h1>
            <p className="m3-body-medium opacity-70" style={{ color: 'var(--on-sv)' }}>
              {agent.context_file} · {agent.source}
            </p>
          </div>
        </div>
      </div>

      {/* Configuration Form */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-xl space-y-6">
          {/* Role Selection */}
          <section>
            <label
              className="m3-label-large block mb-3"
              style={{ color: 'var(--on-sv)' }}
            >
              Role
            </label>
            <div className="grid grid-cols-3 gap-3">
              <RoleOption
                value="principal"
                label="Principal"
                description="Lead agent that assigns work"
                icon="star"
                selected={role === 'principal'}
                onClick={() => setRole('principal')}
              />
              <RoleOption
                value="delegate"
                label="Delegate"
                description="Executes assigned tasks"
                icon="person"
                selected={role === 'delegate'}
                onClick={() => setRole('delegate')}
              />
              <RoleOption
                value="reviewer"
                label="Reviewer"
                description="Reviews and approves work"
                icon="rate_review"
                selected={role === 'reviewer'}
                onClick={() => setRole('reviewer')}
              />
            </div>
          </section>

          {/* YOLO Mode Toggle */}
          <section>
            <div
              className="p-4 rounded-xl border"
              style={{
                borderColor: yoloEnabled ? 'var(--destructive)' : 'var(--outline-variant)',
                background: yoloEnabled ? 'var(--error-cont)' : 'var(--surface-high)',
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">🚀</span>
                  <div>
                    <label
                      className="m3-label-large block"
                      style={{
                        color: yoloEnabled ? 'var(--on-error-cont)' : 'var(--on-sv)',
                      }}
                    >
                      YOLO Mode
                    </label>
                    <p
                      className="m3-body-small opacity-70"
                      style={{
                        color: yoloEnabled ? 'var(--on-error-cont)' : 'var(--on-sv)',
                      }}
                    >
                      Auto-approve all tool calls without prompting
                    </p>
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
                  className="mt-3 p-3 rounded-lg text-sm"
                  style={{
                    background: 'var(--destructive)',
                    color: 'var(--destructive-fg)',
                  }}
                >
                  <Icon name="warning" size={16} className="inline mr-1" />
                  <strong>Warning:</strong> This gives {agent.agent} full autonomy to execute
                  commands, write files, and make changes without asking permission. Use with
                  caution!
                </div>
              )}
            </div>
          </section>

          {/* Source Info */}
          <section>
            <label
              className="m3-label-large block mb-2"
              style={{ color: 'var(--on-sv)' }}
            >
              Configuration Source
            </label>
            <div
              className="p-3 rounded-lg m3-body-medium"
              style={{ background: 'var(--surface-high)', color: 'var(--on-sv)' }}
            >
              {agent.source === 'hub' ? (
                <span className="flex items-center gap-2">
                  <Icon name="cloud" size={18} />
                  Stored in Hub database
                  {agent.updated_at && (
                    <span className="opacity-70">
                      · Updated {new Date(agent.updated_at).toLocaleDateString()}
                    </span>
                  )}
                </span>
              ) : agent.source === 'session.json' ? (
                <span className="flex items-center gap-2">
                  <Icon name="description" size={18} />
                  From session.json file
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Icon name="settings" size={18} />
                  Default configuration
                </span>
              )}
            </div>
          </section>

          {/* Danger Zone */}
          <section className="pt-6 border-t" style={{ borderColor: 'var(--outline-variant)' }}>
            <h3 className="m3-label-large mb-3" style={{ color: 'var(--destructive)' }}>
              Danger Zone
            </h3>

            {!showRemoveConfirm ? (
              <button
                onClick={() => setShowRemoveConfirm(true)}
                className="px-4 py-2 rounded-lg m3-body-medium transition-colors"
                style={{
                  background: 'var(--error-cont)',
                  color: 'var(--on-error-cont)',
                  border: '1px solid var(--destructive)',
                }}
              >
                <Icon name="delete" size={18} className="inline mr-2" />
                Remove Agent
              </button>
            ) : (
              <div
                className="p-4 rounded-lg"
                style={{
                  background: 'var(--error-cont)',
                  border: '1px solid var(--destructive)',
                }}
              >
                <p className="m3-body-medium mb-3" style={{ color: 'var(--on-error-cont)' }}>
                  Are you sure? This will remove {agent.agent} from the project.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleRemove}
                    disabled={isLoading}
                    className="px-4 py-2 rounded-lg m3-body-medium"
                    style={{
                      background: 'var(--destructive)',
                      color: 'var(--destructive-fg)',
                    }}
                  >
                    {isLoading ? 'Removing...' : 'Yes, Remove'}
                  </button>
                  <button
                    onClick={() => setShowRemoveConfirm(false)}
                    className="m3-btn-text"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Footer with Save Button */}
      {hasChanges && (
        <div
          className="p-4 border-t"
          style={{
            borderColor: 'var(--outline-variant)',
            background: 'var(--surface-high)',
          }}
        >
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="m3-btn-filled flex-1"
            >
              {isSaving ? (
                <>
                  <Icon name="progress_activity" size={20} className="animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Icon name="save" size={20} />
                  Save Changes
                </>
              )}
            </button>
            <button
              onClick={() => {
                setRole(agent.role)
                setYoloEnabled(agent.yolo_enabled)
                setHasChanges(false)
              }}
              className="m3-btn-text"
            >
              Discard
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

interface RoleOptionProps {
  value: string
  label: string
  description: string
  icon: string
  selected: boolean
  onClick: () => void
}

function RoleOption({ label, description, icon, selected, onClick }: RoleOptionProps) {
  return (
    <button
      onClick={onClick}
      className="p-4 rounded-xl border-2 text-left transition-all"
      style={{
        background: selected ? 'var(--p-cont)' : 'var(--surface-high)',
        borderColor: selected ? 'var(--primary)' : 'transparent',
      }}
    >
      <Icon
        name={icon}
        size={24}
        className="mb-2"
        style={{ color: selected ? 'var(--primary)' : 'var(--on-sv)' }}
      />
      <div
        className="m3-label-large block mb-1"
        style={{ color: selected ? 'var(--on-p-cont)' : 'var(--on-sv)' }}
      >
        {label}
      </div>
      <div
        className="m3-body-small opacity-70"
        style={{ color: selected ? 'var(--on-p-cont)' : 'var(--on-sv)' }}
      >
        {description}
      </div>
    </button>
  )
}
