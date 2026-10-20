import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { SettingsPage } from '@/components/ui/settings'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Charter } from '@/api/charters'
import { charterSummary as truncatedSummary } from '@/components/charters/charterSummary'
import { charterSummary } from './settingsOptions'

/** Project settings → Charters: authored behaviour and boundaries an agent can be given.
 *
 *  The list printed each charter's raw Markdown ("> **Scope:** … ## You Are Accountable For").
 *  Rows now show the charter's scope as a plain sentence; opening one shows it rendered, in place.
 *
 *  It stays a disclosure, not a reading dialog: two charters must be readable side by side to be
 *  compared, which a modal cannot do. The collapsed row holds a short summary only, so a screen
 *  reader does not read every charter in full. Editing is a separate action, never the row. */

export function ChartersSettings({
  charters,
  boundTo,
  onNew,
  onEdit,
  onDelete,
  deleting,
  notices,
}: {
  charters: Charter[]
  /** The agents a charter is bound to. */
  boundTo: (charter: Charter) => string[]
  onNew: () => void
  onEdit: (charter: Charter) => void
  onDelete: (charter: Charter) => void
  deleting?: boolean
  /** A refused delete, under the page heading. */
  notices?: React.ReactNode
}) {
  // Per id rather than one selection, so two can be compared. Describes what is being read right
  // now, so it is not persisted.
  const [open, setOpen] = React.useState<Set<string>>(() => new Set())
  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current)
      if (!next.delete(id)) next.add(id)
      return next
    })

  return (
    <SettingsPage
      icon="menu_book"
      title="Charters"
      description="What an agent is accountable for and where its authority ends. Give one to an agent in its settings."
      actions={
        <Button variant="primary" size="sm" onClick={onNew}>
          <Icon name="add" size={14} /> New charter
        </Button>
      }
    >
      {notices}
      {charters.length === 0 ? (
        <div className="aw-settings-empty">
          <span className="aw-settings-empty-icon">
            <Icon name="menu_book" size={18} />
          </span>
          <p className="aw-settings-empty-title">No charters yet</p>
          <p className="aw-settings-empty-desc">Write one, then give it to an agent in that agent's settings.</p>
        </div>
      ) : null}
      <ul className="aw-list" aria-label="Charters">
        {charters.map((charter) => {
          const agents = boundTo(charter)
          const expanded = open.has(charter.id)
          const regionId = `charter-content-${charter.id}`
          return (
            <li key={charter.id} className="aw-charter-item" data-open={expanded ? 'true' : 'false'}>
              <div className="aw-list-row aw-list-row-tall aw-reveal-host">
                <button
                  type="button"
                  data-slot="list-open"
                  className="aw-list-open"
                  aria-expanded={expanded}
                  aria-controls={regionId}
                  aria-label={`${expanded ? 'Collapse' : 'Expand'} ${charter.name}`}
                  onClick={() => toggle(charter.id)}
                >
                  <span className="aw-list-title">
                    <span className="aw-history-chevron" data-open={expanded ? 'true' : 'false'}>
                      <Icon name="chevron_right" size={12} />
                    </span>
                    {charter.name}
                  </span>
                  {expanded ? null : <span className="aw-list-sub aw-list-clamp">{truncatedSummary(charterSummary(charter.content)) || 'No content'}</span>}
                </button>
                <span className="aw-reveal-rest aw-list-meta">{agents.length ? agents.join(', ') : 'Not given to an agent'}</span>
                <span className="aw-reveal aw-list-actions">
                  <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Edit ${charter.name}`} title="Edit" onClick={() => onEdit(charter)}>
                    <Icon name="edit" size={13} />
                  </button>
                  <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Delete ${charter.name}`} title="Delete" disabled={deleting} onClick={() => onDelete(charter)}>
                    <Icon name="delete" size={13} />
                  </button>
                </span>
              </div>
              {expanded ? (
                <div id={regionId} className="aw-charter-read aw-charter-inline">
                  {/* A charter is a document with hard-wrapped lines, so no remark-breaks here (chat
                      keeps it); and no rehype plugins, so embedded HTML is never parsed. */}
                  {charter.content.trim() ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{charter.content.replace(/^#\s+.*\n+/, '')}</ReactMarkdown>
                  ) : (
                    <p className="aw-empty-line">This charter has no content, so it contributes nothing to an agent's turn.</p>
                  )}
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>
    </SettingsPage>
  )
}
