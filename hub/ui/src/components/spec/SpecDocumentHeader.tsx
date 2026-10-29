import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import '@/styles/spec-header.css'

export type SpecPhase = 'exploring' | 'approved' | 'archived' | 'current'

const PHASE_LABEL: Record<SpecPhase, string> = {
  exploring: 'Exploring',
  approved: 'Approved',
  archived: 'Archived',
  current: 'Current',
}

const KIND_LABEL: Record<string, string> = {
  'change-spec': 'Change',
  roadmap: 'Roadmap',
  capability: 'Capability',
  baseline: 'Overview',
  'system-map': 'System map',
}

/** The one action the document is waiting for, and why it is the one. */
export interface SpecPrimaryAction {
  label: string
  /** One sentence saying why this is the next step, shown beside the button. */
  reason: string
  onClick: () => void
  disabled?: boolean
  testId?: string
  /** Marks the reason with the state it reports, for a reader that needs to name it. */
  reasonTestId?: string
  reasonState?: string
}

/** The document's header: where it sits, what it is, what it is waiting for.
 *
 *  Replaces eight stacked strips (a banner, an action row mixing a pill with plain-text actions, a
 *  "Created …" log, vault warnings, coverage, drift, a tasks link and a manifest-drift row), each
 *  in its own style, that pushed the document 380px down. Now: a breadcrumb and the actions on
 *  one row, the title with its phase, and `health` (SpecHealthLine) for every fact. One
 *  action is the primary button (Approve, Build…, Fold…); `beforePrimary` carries the controls that
 *  sit beside it (Check, Approve and build…); the rest are in the overflow menu, named for what
 *  they do.
 *
 *  Hosts with more to say pass it in: `menu` (more overflow items), `badges` (beside the phase, such
 *  as the flow the document runs), `tools` (icon buttons after the menu), `beforePrimary` (a control
 *  that qualifies the primary action) and `messages` (what the document's controls produced: a
 *  refusal, the gaps approval found). `onOpenLocation` makes
 *  the breadcrumb open the document search. */
export function SpecDocumentHeader({
  path,
  title,
  kind,
  phase,
  primary,
  health,
  onArchive,
  onReopen,
  onDelete,
  onCopyPath,
  menu,
  badges,
  tools,
  beforePrimary,
  messages,
  onOpenLocation,
}: {
  path: string
  title: string
  kind: string
  /** Absent for a document the Hub keeps no record of (no phase is known). */
  phase?: SpecPhase | null
  primary?: SpecPrimaryAction | null
  health: React.ReactNode
  onArchive?: () => void
  onReopen?: () => void
  onDelete?: () => void
  onCopyPath: () => void
  menu?: React.ReactNode
  badges?: React.ReactNode
  tools?: React.ReactNode
  beforePrimary?: React.ReactNode
  messages?: React.ReactNode
  onOpenLocation?: () => void
}) {
  const crumbs = path.replace(/\/spec\.json$/, '').split('/')
  const crumbTrail = crumbs.map((part, i) => (
    <React.Fragment key={i}>
      {i > 0 ? <Icon name="chevron_right" size={11} className="aw-spec-crumb-sep" /> : null}
      <span className={i === crumbs.length - 1 ? 'aw-spec-crumb-current' : 'aw-spec-crumb'}>{part}</span>
    </React.Fragment>
  ))
  return (
    <header className="aw-spec-head" data-testid="spec-document-header">
      <div className="aw-spec-head-bar">
        {onOpenLocation ? (
          <button
            type="button"
            data-slot="spec-crumbs"
            className="aw-spec-crumbs aw-spec-crumbs-button"
            data-testid="spec-document-breadcrumb"
            title={`${path} — choose another document (Ctrl+Shift+K)`}
            aria-label={`${title} — choose another document`}
            onClick={onOpenLocation}
          >
            {crumbTrail}
            <Icon name="expand_more" size={12} className="aw-spec-crumb-sep" />
          </button>
        ) : (
          <nav className="aw-spec-crumbs" aria-label="Document location" title={path}>
            {crumbTrail}
          </nav>
        )}
        <div className="aw-spec-actions">
          {beforePrimary}
          {primary ? (
            <>
              <span className="aw-spec-reason" data-testid={primary.reasonTestId} data-state={primary.reasonState}>
                {primary.reason}
              </span>
              <Button variant="primary" size="sm" data-testid={primary.testId} disabled={primary.disabled} onClick={primary.onClick}>
                {primary.label}
              </Button>
            </>
          ) : null}
          <Menu>
            <MenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="More actions" title="More actions" data-testid="spec-more-actions">
                <Icon name="more_horiz" size={15} />
              </Button>
            </MenuTrigger>
            <MenuContent>
              <MenuItem icon="content_copy" onSelect={onCopyPath}>
                Copy file path
              </MenuItem>
              {menu}
              {onReopen || onArchive || onDelete ? <MenuSeparator /> : null}
              {onReopen ? (
                <MenuItem icon="restart_alt" data-testid="spec-reopen" onSelect={onReopen}>
                  Reopen for changes
                </MenuItem>
              ) : null}
              {onArchive ? (
                <MenuItem icon="archive" data-testid="spec-archive" onSelect={onArchive}>
                  Archive
                </MenuItem>
              ) : null}
              {onDelete ? (
                <MenuItem icon="delete" destructive data-testid="spec-delete" onSelect={onDelete}>
                  Delete document…
                </MenuItem>
              ) : null}
            </MenuContent>
          </Menu>
          {tools ? <span className="aw-spec-tools">{tools}</span> : null}
        </div>
      </div>
      <div className="aw-spec-titlebar">
        <h1 className="aw-spec-title">{title}</h1>
        {phase ? (
          <span className="aw-spec-phase" data-phase={phase} data-testid="spec-phase">
            {PHASE_LABEL[phase] ?? phase}
          </span>
        ) : null}
        <span className="aw-spec-kind">{KIND_LABEL[kind] ?? kind}</span>
        {badges}
      </div>
      {health}
      {messages ? <div className="aw-spec-messages">{messages}</div> : null}
    </header>
  )
}
