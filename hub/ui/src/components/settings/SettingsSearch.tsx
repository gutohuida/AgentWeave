import { useAgents } from '@/api/agents'
import { Icon } from '@/components/common/Icon'
import { goTo } from '@/lib/navigation'
import { SCOPE_LABEL, searchSettings, settingDestination, type SettingEntry } from '@/lib/settingsIndex'
import { useConfigStore } from '@/store/configStore'

/** The search field above a settings screen's section list. What it finds is `searchSettings`
 *  (the one matching rule, shared with the command palette). */
export function SettingsSearchBox({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="aw-settings-search">
      <Icon name="search" size={13} className="aw-settings-search-icon" />
      <input
        type="search"
        data-testid="settings-search"
        className="aw-settings-search-input"
        placeholder="Search settings"
        aria-label="Search settings"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && value) {
            event.stopPropagation()
            onChange('')
          }
        }}
      />
    </div>
  )
}

/** The results, in place of the section the operator was reading. `agent` is the agent whose
 *  settings are open, if any: choosing an agent setting itself opens it for that agent. */
export function SettingsSearchResults({
  query,
  agent,
  onChosen,
}: {
  query: string
  agent?: string
  /** Called after a result was chosen, so the screen can clear the search and land. */
  onChosen: () => void
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: roster = [], error: rosterError } = useAgents()
  const matches = searchSettings(query)
  const words = query.trim()

  const choose = (entry: SettingEntry, agentName?: string | null) => {
    const destination = settingDestination(entry, projectId || null, agentName)
    if (!destination) return
    goTo(destination)
    onChosen()
  }

  if (words.replace(/\s+/g, '').length < 2) {
    return (
      <div className="aw-settings-search-results">
        <p className="aw-settings-search-note" data-testid="settings-search-hint">Type at least two letters to search every setting.</p>
      </div>
    )
  }
  if (matches.length === 0) {
    return (
      <div className="aw-settings-search-results">
        <p className="aw-settings-search-note" data-testid="settings-search-empty">
          No setting matches “{words}”.
        </p>
      </div>
    )
  }
  return (
    <div className="aw-settings-search-results">
      {rosterError ? (
        <p className="aw-settings-search-note" role="alert" data-testid="settings-search-agents-error">
          The agent list could not be loaded, so agents are not shown under agent settings.
        </p>
      ) : null}
      <ul className="aw-settings-search-list" aria-label="Matching settings">
        {matches.map(({ entry }) => {
          const opens = entry.scope === 'agent' ? (agent ?? roster[0]?.name ?? null) : null
          return (
            <li
              key={`${entry.scope}/${entry.section}/${entry.label}`}
              className="aw-settings-search-item"
              data-testid="settings-search-result"
              data-scope={entry.scope}
              data-section={entry.sectionLabel}
              data-label={entry.label}
            >
              <button
                type="button"
                className="aw-settings-search-open"
                data-testid="settings-search-open"
                disabled={entry.scope === 'agent' && !opens}
                onClick={() => choose(entry, opens)}
              >
                <span className="aw-settings-search-label">{entry.label}</span>
                <span className="aw-settings-search-where">
                  {entry.scope === 'agent' ? 'Agent settings' : `${SCOPE_LABEL[entry.scope]} settings`} · {entry.sectionLabel}
                </span>
                <span className="aw-settings-search-desc">{entry.description}</span>
              </button>
              {entry.scope === 'agent' && roster.length > 0 ? (
                <div className="aw-settings-search-agents">
                  <span className="aw-settings-search-agents-label">Agents</span>
                  {roster.map((candidate) => (
                    <button
                      key={candidate.name}
                      type="button"
                      className="aw-settings-search-agent"
                      data-testid="settings-search-agent"
                      data-agent={candidate.name}
                      onClick={() => choose(entry, candidate.name)}
                    >
                      {candidate.name}
                    </button>
                  ))}
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
