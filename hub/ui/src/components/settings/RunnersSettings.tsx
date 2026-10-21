import type * as React from 'react'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { SettingsPage } from '@/components/ui/settings'
import type { Runner } from '@/api/runners'

/** Project settings → Runners: which CLI and model an agent launches with. Each row carries the
 *  provider's mark and the model in words; edit and delete appear on hover or focus instead of
 *  sitting on every row. */

const CLI_LABEL: Record<string, string> = { claude: 'Claude Code', codex: 'Codex CLI', copilot: 'GitHub Copilot CLI' }

export function RunnersSettings({
  runners,
  modelLabel,
  usedBy,
  onNew,
  onEdit,
  onDelete,
  deleting,
  notices,
}: {
  runners: Runner[]
  /** A model id in words ("Opus 5.5"); null leaves the id. */
  modelLabel: (runner: Runner) => string | null
  /** How many agents and jobs use each runner, for the row's meta. */
  usedBy: (runner: Runner) => number
  onNew: () => void
  onEdit: (runner: Runner) => void
  onDelete: (runner: Runner) => void
  /** A delete is in flight: the delete buttons wait for it. */
  deleting?: boolean
  /** A refused delete, under the page heading. */
  notices?: React.ReactNode
}) {
  return (
    <SettingsPage
      icon="terminal"
      title="Runners"
      description="Which CLI and model an agent launches with. Bind one to an agent in its settings."
      actions={
        <Button variant="primary" size="sm" onClick={onNew}>
          <Icon name="add" size={14} /> New runner
        </Button>
      }
    >
      {notices}
      {runners.length === 0 ? (
        <div className="aw-settings-empty">
          <span className="aw-settings-empty-icon">
            <Icon name="terminal" size={18} />
          </span>
          <p className="aw-settings-empty-title">No runners yet</p>
          <p className="aw-settings-empty-desc">One is made for each supported CLI the first time the Hub starts. Add your own to vary the model or the name.</p>
        </div>
      ) : null}
      <ul className="aw-list" aria-label="Runners">
        {runners.map((runner) => {
          const isDefault = runner.name.endsWith('(default)')
          const name = isDefault ? runner.name.replace(/\s*\(default\)$/, '') : runner.name
          const uses = usedBy(runner)
          return (
            <li key={runner.id} className="aw-list-row aw-reveal-host">
              <span className="aw-list-mark">
                <ProviderMark provider={runner.cli} label={CLI_LABEL[runner.cli] ?? runner.cli} size={16} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="aw-list-title">
                  {name}
                  {isDefault ? <span className="aw-tag">Default</span> : null}
                  {runner.provider_config ? (
                    <span className="aw-tag" title={`Runs go to ${runner.provider_config.base_url} with the key in $${runner.provider_config.api_key_var}`}>
                      Anthropic API
                    </span>
                  ) : null}
                </span>
                <span className="aw-list-sub">
                  {CLI_LABEL[runner.cli] ?? runner.cli} · {runner.model ? (modelLabel(runner) ?? runner.model) : 'the CLI’s own model'}
                  {runner.model_unrecognised ? (
                    <span className="aw-list-warn" title="The catalog does not declare this model for this CLI. The runner still works; editing it keeps the model unless you change it.">
                      {' '}
                      · model not in the catalog
                    </span>
                  ) : null}
                </span>
              </span>
              <span className="aw-reveal-rest aw-list-meta">{uses ? `${uses} using it` : 'Unused'}</span>
              <span className="aw-reveal aw-list-actions">
                <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Edit ${runner.name}`} title="Edit" onClick={() => onEdit(runner)}>
                  <Icon name="edit" size={13} />
                </button>
                <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Delete ${runner.name}`} title="Delete" disabled={deleting} onClick={() => onDelete(runner)}>
                  <Icon name="delete" size={13} />
                </button>
              </span>
            </li>
          )
        })}
      </ul>
    </SettingsPage>
  )
}
