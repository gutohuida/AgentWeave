import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { Button } from '@/components/ui/button'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { formatAgo } from '@/lib/format'
import { useEnter } from './hooks'
import { SpecNoticeBadge, type HeaderNotice } from './SpecNotices'
import {
  actionsFor,
  JOURNEY,
  phaseLabel,
  journeyIndex,
  SHOWN_LABEL,
  type ShownState,
  type CheckFinding,
  type CheckState,
  type SpecAction,
  type SpecDocumentView,
} from './model'
import '@/styles/spec-page.css'

/** What a container adds to the header from the document's phase controls: every decision the Hub's
 *  document offers that the page's own buttons do not draw. One source, so none can be dropped. */
export interface HeaderChrome {
  /** Menu items for the More menu (Start a flow, Retire, Refresh). */
  moreItems?: React.ReactNode
  /** Beside the phase: the flow the document runs, an archived marker, Place under. */
  badges?: React.ReactNode
  /** Before the actions: the Draft the next slice switch. */
  draftNext?: React.ReactNode
  /** The journey step and size control, opened from the phase badge while a change is written. */
  journey?: React.ReactNode
}

export interface SpecPageHeaderProps {
  chrome?: HeaderChrome
  doc: SpecDocumentView
  check: CheckState
  /** The running build's number, when there is one: the "open the build" action names it. */
  runningBuild?: number | null
  now: Date
  /** One column (the conversation's panel): the crumbs, title and actions wrap. */
  compact?: boolean
  /** Placed before the breadcrumb: the document switcher, when the list is not a column. */
  leading?: React.ReactNode
  /** Placed after the actions: the outline menu, in the panel. */
  trailing?: React.ReactNode
  canBack: boolean
  canForward: boolean
  onBack: () => void
  onForward: () => void
  onAction: (action: SpecAction) => void
  onJumpToFindings: () => void
  onOpenDocument: (path: string, anchor?: string) => void
  onCopyLink: () => void
  onCopyPath: () => void
  /** Left out when the document cannot be archived (a capability, a document already archived). */
  onArchive?: () => void
  /** Left out when the document must not be deleted (the corpus depends on it). */
  onDelete?: () => void
  /** Everything the document has to tell the operator, behind one count (FR-7). */
  notices?: HeaderNotice[]
  /** The document's health facts, drawn in the second row beside the phase. */
  health?: React.ReactNode
  /** The body is scrolled: the header shrinks to one line (FR-4). */
  condensed?: boolean
  onExpand?: () => void
}

/** The document's header (spec `the-spec-header-redesigned`, design B), two rows: where it sits
 *  and what can be done, with every message behind one count; then the title with its phase, the
 *  journey as four knots and the health facts. Once the body is scrolled it is one line: the title,
 *  the phase, the count and the actions; clicking that line expands it again. */
export function SpecPageHeader(props: SpecPageHeaderProps) {
  const { doc, check, compact, now } = props
  const actions = actionsFor(doc.state, doc.kind, doc.foldReady === true)
  const notices = props.notices ?? []
  const shownState = doc.state === 'ready' ? 'writing' : doc.shown
  // A click on the condensed line expands it, unless it landed on one of its controls.
  const onBarClick = (event: React.MouseEvent) => {
    if (!props.condensed || !props.onExpand) return
    if ((event.target as Element).closest('button, a, input, select, [role="menu"], .aw-notice-pop')) return
    props.onExpand()
  }
  return (
    <header
      className="aw-sp-head"
      data-testid="spec-document-header"
      data-compact={compact ? 'true' : 'false'}
      data-condensed={props.condensed ? 'true' : 'false'}
    >
      <div className="aw-sp-head-bar" onClick={onBarClick}>
        {props.leading}
        <div className="aw-sp-history" role="group" aria-label="History">
          <button data-slot="icon-button" type="button" className="aw-icon-button" disabled={!props.canBack} onClick={props.onBack} aria-label="Back" title="Back">
            <Icon name="arrow_left" size={14} />
          </button>
          <button data-slot="icon-button" type="button" className="aw-icon-button" disabled={!props.canForward} onClick={props.onForward} aria-label="Forward" title="Forward">
            <Icon name="arrow_forward" size={14} />
          </button>
        </div>
        {props.condensed ? (
          <button type="button" className="aw-sp-head-condensed-title" data-testid="spec-header-condensed" onClick={props.onExpand} title="Show the whole header">
            <strong>{doc.title}</strong>
            <span className="aw-sp-phase" data-state={shownState}>
              {phaseLabel(doc, shownState)}
            </span>
          </button>
        ) : null}
        <nav className="aw-sp-crumbs" aria-label="Where this document sits">
          {doc.roadmap ? (
            <>
              <button data-slot="crumb" type="button" className="aw-sp-crumb" onClick={() => props.onOpenDocument(doc.roadmap!.path, doc.roadmap!.sliceKey ? `slice-${doc.roadmap!.sliceKey}` : undefined)} title="Open the roadmap at this slice">
                <Icon name="list_tree" size={13} />
                <span className="truncate">{doc.roadmap.title}</span>
              </button>
              <Icon name="chevron_right" size={12} className="aw-sp-crumb-sep" />
              <span className="aw-sp-crumb-current truncate">{doc.roadmap.sliceTitle}</span>
            </>
          ) : (
            <span className="aw-sp-crumb-current truncate">{kindLabel(doc.kind)}</span>
          )}
        </nav>
        {doc.roadmap ? (
          <div className="aw-sp-slicenav" role="group" aria-label="Neighbouring slices">
            <button
              data-slot="icon-button"
              type="button"
              className="aw-icon-button"
              disabled={!doc.roadmap.previous}
              onClick={() => doc.roadmap?.previous && props.onOpenDocument(doc.roadmap.previous.path)}
              aria-label="Previous slice"
              title={doc.roadmap.previous ? `Previous slice: ${doc.roadmap.previous.title}` : 'This is the first slice'}
            >
              <Icon name="expand_less" size={14} />
            </button>
            <button
              data-slot="icon-button"
              type="button"
              className="aw-icon-button"
              disabled={!doc.roadmap.next}
              onClick={() => doc.roadmap?.next && props.onOpenDocument(doc.roadmap.next.path)}
              aria-label="Next slice"
              title={doc.roadmap.next ? `Next slice: ${doc.roadmap.next.title}` : 'This is the last slice'}
            >
              <Icon name="expand_more" size={14} />
            </button>
          </div>
        ) : null}
        <span className="aw-sp-head-spacer" />
        <div className="aw-sp-actions">
          <SpecNoticeBadge notices={notices} />
          {props.chrome?.draftNext}
          {actions.secondary.includes('check') ? <CheckButton check={check} onCheck={() => props.onAction('check')} /> : null}
          <PrimaryAction
            action={actions.primary}
            check={check}
            runningBuild={props.runningBuild ?? null}
            offersApproveAndBuild={actions.secondary.includes('approve-and-build')}
            onAction={props.onAction}
          />
          <MoreMenu {...props} />
          {props.trailing}
        </div>
      </div>

      {props.condensed ? null : (
        <div className="aw-sp-head-row2">
          <h1 className="aw-sp-title">{doc.title}</h1>
          <div className="aw-sp-meta">
            {/* The phase, not the check: a clean check makes a document ready, still being written. */}
            {props.chrome?.journey ? (
              <PhaseWithJourney label={phaseLabel(doc, shownState)} state={shownState} key={doc.shown}>
                {props.chrome.journey}
              </PhaseWithJourney>
            ) : (
              <span className="aw-sp-phase" data-state={shownState} key={doc.shown}>
                {phaseLabel(doc, shownState)}
              </span>
            )}
            {doc.state === 'current' ? null : <MiniJourney state={doc.state === 'ready' ? doc.state : doc.shown} />}
            {/* The crumb names the kind when the document sits in no roadmap: said once. */}
            {doc.roadmap ? <span className="aw-sp-meta-fact">{kindLabel(doc.kind)}</span> : null}
            {props.chrome?.badges}
            <span className="aw-sp-meta-fact" title={doc.updatedAt}>
              Changed {formatAgo(doc.updatedAt, now)}
            </span>
            <CheckResult check={check} onJump={props.onJumpToFindings} />
          </div>
          {/* One line under the title (`header-fits`): what does not fit scrolls sideways. */}
          {props.health ? (
            <div className="aw-sp-head-factline" data-testid="spec-header-factline">
              {props.health}
            </div>
          ) : null}
        </div>
      )}
    </header>
  )
}

function MoreMenu(props: SpecPageHeaderProps) {
  const { doc } = props
  return (
    <Menu>
      <MenuTrigger asChild>
        <button data-slot="icon-button" type="button" className="aw-icon-button aw-sp-more" aria-label="More actions" title="More actions">
          <Icon name="more_horiz" size={15} />
        </button>
      </MenuTrigger>
      <MenuContent>
        <MenuItem icon="link" onSelect={props.onCopyLink}>
          Copy link to this document
        </MenuItem>
        <MenuItem icon="content_copy" onSelect={props.onCopyPath}>
          Copy its path
        </MenuItem>
        {props.chrome?.moreItems}
        {(doc.state === 'approved' || doc.state === 'building') && doc.phase !== 'current' ? (
          <MenuItem icon="edit" onSelect={() => props.onAction('reopen')}>
            Reopen for changes
          </MenuItem>
        ) : null}
        {props.onArchive || props.onDelete ? <MenuSeparator /> : null}
        {props.onArchive ? (
          <MenuItem icon="archive" onSelect={props.onArchive}>
            Archive
          </MenuItem>
        ) : null}
        {props.onDelete ? (
          <MenuItem icon="delete" destructive onSelect={props.onDelete}>
            Delete…
          </MenuItem>
        ) : null}
      </MenuContent>
    </Menu>
  )
}

/** The journey as four knots beside the phase: the ribbon's thread, without its row. */
function MiniJourney({ state }: { state: ShownState }) {
  const at = journeyIndex(state)
  const finished = state === 'archived' || state === 'done'
  const names = JOURNEY.map((s) => s.label).join(' → ')
  return (
    <span className="aw-sp-minijourney" role="img" aria-label={`Journey: ${names}; now ${SHOWN_LABEL[state]}`} title={names}>
      {JOURNEY.map((stop, i) => (
        <React.Fragment key={stop.key}>
          {i > 0 ? <span className="aw-sp-minijourney-link" data-reached={i <= at ? 'done' : 'ahead'} /> : null}
          <span className="aw-sp-minijourney-knot" data-reached={i < at || (i === at && finished) ? 'done' : i === at ? 'current' : 'ahead'} />
        </React.Fragment>
      ))}
    </span>
  )
}

function kindLabel(kind: SpecDocumentView['kind']): string {
  return { 'change-spec': 'Change', roadmap: 'Roadmap', capability: 'Capability', baseline: 'Baseline', 'system-map': 'System map' }[kind]
}

function CheckButton({ check, onCheck, primary }: { check: CheckState; onCheck: () => void; primary?: boolean }) {
  const checking = check.status === 'checking'
  return (
    <Button
      variant={primary ? 'primary' : 'ghost'}
      size="sm"
      onClick={onCheck}
      disabled={checking}
      aria-busy={checking}
      title="Validate the document against its rules. Never changes its phase."
    >
      {checking ? <LoadingThread size="control" label="Checking" className="aw-sp-check-loader" /> : <Icon name="fact_check" size={14} />}
      {checking ? 'Checking…' : check.status === 'done' ? 'Check again' : 'Check'}
    </Button>
  )
}

/** The last check's result, as a pill that jumps to the first finding. */
function CheckResult({ check, onJump }: { check: CheckState; onJump: () => void }) {
  if (check.status !== 'done') return null
  return <CheckPill findings={check.findings} onJump={onJump} key={check.at} />
}

function CheckPill({ findings, onJump }: { findings: CheckFinding[]; onJump: () => void }) {
  const clearRef = useEnter<HTMLSpanElement>('pop')
  const pillRef = useEnter<HTMLButtonElement>('pop')
  const blocking = findings.filter((f) => f.severity === 'blocking').length
  const warnings = findings.length - blocking
  if (!findings.length) {
    return (
      <span className="aw-sp-check-pill" data-tone="clear" ref={clearRef}>
        <Icon name="check" size={12} />
        Nothing blocks approval
      </span>
    )
  }
  return (
    <button data-slot="check-pill" type="button" className="aw-sp-check-pill" data-tone={blocking ? 'blocking' : 'warning'} onClick={onJump} ref={pillRef} title="Show what the check found">
      {blocking ? (
        <span className="aw-sp-check-count" data-tone="blocking">
          {blocking} blocking
        </span>
      ) : null}
      {blocking && warnings ? <span className="aw-sp-dot-sep" aria-hidden="true" /> : null}
      {warnings ? (
        <span className="aw-sp-check-count" data-tone="warning">
          {warnings} {warnings === 1 ? 'warning' : 'warnings'}
        </span>
      ) : null}
      <Icon name="arrow_downward" size={11} />
    </button>
  )
}

function PrimaryAction({
  action,
  check,
  runningBuild,
  offersApproveAndBuild,
  onAction,
}: {
  action: SpecAction | null
  check: CheckState
  runningBuild: number | null
  offersApproveAndBuild: boolean
  onAction: (action: SpecAction) => void
}) {
  switch (action) {
    case 'check':
      return <CheckButton check={check} onCheck={() => onAction('check')} primary />
    case 'approve':
      return (
        <SplitButton
          icon="verified"
          label="Approve"
          title="Accept the plan: its tasks are laid out, nothing starts."
          onClick={() => onAction('approve')}
          menu={offersApproveAndBuild ? [{ icon: 'play_arrow', label: 'Approve and build…', detail: 'Accept the plan and choose how to build it.', onSelect: () => onAction('approve-and-build') }] : []}
        />
      )
    case 'build':
      return (
        <SplitButton
          icon="play_arrow"
          label="Build…"
          title="Choose who builds it, at which level, and start."
          onClick={() => onAction('build')}
          menu={[]}
        />
      )
    case 'open-build':
      return (
        <SplitButton
          icon="live"
          label={runningBuild ? `Build ${runningBuild} running` : 'Build running'}
          title="Show the running build"
          onClick={() => onAction('open-build')}
          menu={[]}
        />
      )
    case 'fold':
      return (
        <Button variant="primary" size="sm" data-testid="fold-open" onClick={() => onAction('fold')} title="Shipped, not yet in a capability: fold its requirements into the capability they change.">
          <Icon name="git_merge" size={14} />
          Fold into capability…
        </Button>
      )
    case 'reopen':
      return (
        <Button variant="primary" size="sm" onClick={() => onAction('reopen')}>
          <Icon name="restart_alt" size={14} />
          Reopen for changes
        </Button>
      )
    default:
      return null
  }
}

interface SplitItem {
  icon: string
  label: string
  detail?: string
  onSelect: () => void
}

/** A primary button with the alternatives behind its chevron. */
function SplitButton({ icon, label, title, onClick, menu }: { icon: string; label: string; title?: string; onClick: () => void; menu: SplitItem[] }) {
  return (
    <span className="aw-sp-split" data-split={menu.length ? 'true' : 'false'}>
      <Button variant="primary" size="sm" onClick={onClick} title={title} className="aw-sp-split-main">
        {icon === 'live' ? <span className="aw-sp-live" aria-hidden="true" /> : <Icon name={icon} size={14} />}
        {label}
      </Button>
      {menu.length ? (
        <Menu>
          <MenuTrigger asChild>
            <Button variant="primary" size="sm" className="aw-sp-split-more" aria-label="More ways to do this">
              <Icon name="expand_more" size={14} />
            </Button>
          </MenuTrigger>
          <MenuContent>
            {menu.map((item) => (
              <MenuItem key={item.label} icon={item.icon} onSelect={item.onSelect}>
                <span className="block">{item.label}</span>
                {item.detail ? <span className="aw-menu-item-detail">{item.detail}</span> : null}
              </MenuItem>
            ))}
          </MenuContent>
        </Menu>
      ) : null}
    </span>
  )
}

/** The phase badge, while a change is written: it names the step, and opens the control that moves
 *  the step or changes the size. The list floats over the body, so it adds no height. */
function PhaseWithJourney({ label, state, children }: { label: string; state: ShownState; children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false)
  const root = React.useRef<HTMLSpanElement>(null)
  React.useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const target = e.target as Element | null
      if (!root.current || root.current.contains(target)) return
      if (target?.closest?.('[role="dialog"], [role="menu"], [role="listbox"]')) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <span className="aw-sp-phase-wrap" ref={root}>
      <button
        type="button"
        className="aw-sp-phase"
        data-state={state}
        data-testid="spec-phase-journey"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((o) => !o)}
        title="Move the step or change the size"
      >
        {label}
      </button>
      {open ? (
        <div className="aw-notice-pop aw-pop aw-sp-phase-pop" data-state="open" role="region" aria-label="Journey step and size">
          <div className="aw-notice-body">{children}</div>
        </div>
      ) : null}
    </span>
  )
}
