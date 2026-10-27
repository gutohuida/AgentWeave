import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
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

export type Rigor = 'sketch' | 'contract' | 'gate'

const RIGOR_OPTIONS: Array<{ value: Rigor; label: string; detail: string }> = [
  { value: 'sketch', label: 'Sketch', detail: 'Blocks nothing' },
  { value: 'contract', label: 'Contract', detail: 'Stated, not enforced' },
  { value: 'gate', label: 'Gate', detail: 'Unverified work cannot be approved' },
]

/** The rigor chip as a choice of the three rigors: what the Hub does about work that ignores the document. */
export function RigorChip({ rigor, rigorChoice }: { rigor: string; rigorChoice: { value: Rigor; onChange: (rigor: Rigor) => void; disabled?: boolean } }) {
  const rigorLabel = `${rigor[0]!.toUpperCase() + rigor.slice(1)} rigor`
  return (
    <DropdownMenu.Root>
            <DropdownMenu.Trigger
              data-slot="spec-chip"
              className="aw-spec-chip"
              data-testid="spec-rigor"
              data-value={rigorChoice.value}
              disabled={rigorChoice.disabled}
              aria-label={`Enforcement: ${rigorLabel}`}
              title="How strictly approval checks this document"
            >
              {rigorLabel}
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="start" sideOffset={6} collisionPadding={12} className="aw-menu aw-pop" style={{ minWidth: 260 }}>
                <DropdownMenu.Label className="aw-menu-label">Enforcement</DropdownMenu.Label>
                <DropdownMenu.RadioGroup value={rigorChoice.value} onValueChange={(next) => rigorChoice.onChange(next as Rigor)}>
                  {RIGOR_OPTIONS.map((option) => (
                    <DropdownMenu.RadioItem key={option.value} value={option.value} className="aw-menu-item" data-two-line="true">
                      <span className="aw-menu-item-icon" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{option.label}</span>
                        <span className="aw-menu-item-detail">{option.detail}</span>
                      </span>
                      <DropdownMenu.ItemIndicator className="aw-menu-check">
                        <Icon name="check" size={14} />
                      </DropdownMenu.ItemIndicator>
                    </DropdownMenu.RadioItem>
                  ))}
                </DropdownMenu.RadioGroup>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
  )
}

/** The document's header: where it sits, what it is, what it is waiting for.
 *
 *  Replaces eight stacked strips (a banner, an action row mixing a pill with plain-text actions, a
 *  "Created …" log, vault warnings, coverage, drift, a tasks link and a manifest-drift row), each
 *  in its own style, that pushed the document 380px down. Now: a breadcrumb and the actions on
 *  one row, the title with its phase and rigor, and `health` (SpecHealthLine) for every fact. One
 *  action is the primary button (Approve, Build…, Fold…); `beforePrimary` carries the controls that
 *  sit beside it (Check, Approve and build…); the rest are in the overflow menu, named for what
 *  they do.
 *
 *  Hosts with more to say pass it in: `menu` (more overflow items), `badges` (beside the phase, such
 *  as the flow the document runs), `tools` (icon buttons after the menu), `beforePrimary` (a control
 *  that qualifies the primary action) and `messages` (what the document's controls produced: a
 *  refusal, the gaps approval found, a rigor change waiting for its reason). `onOpenLocation` makes
 *  the breadcrumb open the document search. */
export function SpecDocumentHeader({
  path,
  title,
  kind,
  phase,
  rigor,
  primary,
  health,
  onArchive,
  onReopen,
  onDelete,
  onCopyPath,
  onRigorChange,
  rigorChoice,
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
  /** Absent for a document the Hub keeps no record of (nothing enforces it). */
  rigor?: string | null
  primary?: SpecPrimaryAction | null
  health: React.ReactNode
  onArchive?: () => void
  onReopen?: () => void
  onDelete?: () => void
  onCopyPath: () => void
  /** A rigor menu with nothing behind it (the mock); `rigorChoice` is the working control. */
  onRigorChange?: () => void
  /** The rigor chip as a choice of the three rigors. */
  rigorChoice?: { value: Rigor; onChange: (rigor: Rigor) => void; disabled?: boolean }
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
  const rigorLabel = rigor ? `${rigor[0]!.toUpperCase() + rigor.slice(1)} rigor` : ''
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
              {onRigorChange && !rigorChoice ? (
                <MenuItem icon="tag" onSelect={onRigorChange}>
                  Change rigor…
                </MenuItem>
              ) : null}
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
        {!rigor ? null : rigorChoice ? (
          <RigorChip rigor={rigor} rigorChoice={rigorChoice} />
        ) : (
          <button type="button" data-slot="spec-chip" className="aw-spec-chip" onClick={onRigorChange} title="How strictly approval checks this document">
            {rigorLabel}
          </button>
        )}
        <span className="aw-spec-kind">{KIND_LABEL[kind] ?? kind}</span>
        {badges}
      </div>
      {health}
      {messages ? <div className="aw-spec-messages">{messages}</div> : null}
    </header>
  )
}
