import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { Button } from '@/components/ui/button'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { formatAgo } from '@/lib/format'
import { RigorChip, type Rigor } from '../SpecDocumentHeader'
import { useEnter } from './hooks'
import {
  actionsFor,
  JOURNEY,
  journeyIndex,
  STATE_LABEL,
  type CheckFinding,
  type CheckState,
  type DocState,
  type SpecAction,
  type SpecDocumentView,
} from './model'
import '@/styles/spec-page.css'

/** What a container adds to the header from the document's phase controls: every decision the Hub's
 *  document offers that the page's own buttons do not draw. One source, so none can be dropped. */
export interface HeaderChrome {
  /** Menu items for the More menu (Start a flow, Retire, Rigor history, Refresh). */
  moreItems?: React.ReactNode
  /** Beside the phase: the flow the document runs, an archived marker, Place under. */
  badges?: React.ReactNode
  /** Before the actions: the Draft the next slice switch. */
  draftNext?: React.ReactNode
  /** How strictly approval checks the document, as a choice of three. */
  rigor?: { value: Rigor; onChange: (rigor: Rigor) => void; disabled?: boolean }
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
  onOpenDocument: (path: string) => void
  onCopyLink: () => void
  onCopyPath: () => void
  /** Left out when the document cannot be archived (a capability, a document already archived). */
  onArchive?: () => void
  /** Left out when the document must not be deleted (the corpus depends on it). */
  onDelete?: () => void
}

/** The document's header: where it sits (roadmap › slice, previous and next slice), its title and
 *  phase, the journey ribbon, and the actions open to it as buttons, one primary (FR-1). */
export function SpecPageHeader(props: SpecPageHeaderProps) {
  const { doc, check, compact, now } = props
  const actions = actionsFor(doc.state, doc.kind, doc.foldReady === true)
  return (
    <header className="aw-sp-head" data-testid="spec-document-header" data-compact={compact ? 'true' : 'false'}>
      <div className="aw-sp-head-bar">
        {props.leading}
        <div className="aw-sp-history" role="group" aria-label="History">
          <button data-slot="icon-button" type="button" className="aw-icon-button" disabled={!props.canBack} onClick={props.onBack} aria-label="Back" title="Back">
            <Icon name="arrow_left" size={14} />
          </button>
          <button data-slot="icon-button" type="button" className="aw-icon-button" disabled={!props.canForward} onClick={props.onForward} aria-label="Forward" title="Forward">
            <Icon name="arrow_forward" size={14} />
          </button>
        </div>
        <nav className="aw-sp-crumbs" aria-label="Where this document sits">
          {doc.roadmap ? (
            <>
              <button data-slot="crumb" type="button" className="aw-sp-crumb" onClick={() => props.onOpenDocument(doc.roadmap!.path)} title="Open the roadmap">
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
      </div>

      <div className="aw-sp-head-main">
        <div className="aw-sp-head-text">
          <h1 className="aw-sp-title">{doc.title}</h1>
          <div className="aw-sp-meta">
            {/* The phase, not the check: a clean check makes a document ready, still being written. */}
            <span className="aw-sp-phase" data-state={doc.state === 'ready' ? 'writing' : doc.state} key={doc.state}>
              {STATE_LABEL[doc.state === 'ready' ? 'writing' : doc.state]}
            </span>
            <span className="aw-sp-meta-fact">{kindLabel(doc.kind)}</span>
            {props.chrome?.rigor ? <RigorChip rigor={props.chrome.rigor.value} rigorChoice={props.chrome.rigor} /> : null}
            {props.chrome?.badges}
            <span className="aw-sp-meta-fact" title={doc.updatedAt}>
              Changed {formatAgo(doc.updatedAt, now)}
            </span>
            <CheckResult check={check} onJump={props.onJumpToFindings} />
          </div>
        </div>
        <div className="aw-sp-actions">
          {props.chrome?.draftNext}
          {actions.secondary.includes('check') ? <CheckButton check={check} onCheck={() => props.onAction('check')} /> : null}
          <PrimaryAction
            action={actions.primary}
            check={check}
            runningBuild={props.runningBuild ?? null}
            offersApproveAndBuild={actions.secondary.includes('approve-and-build')}
            onAction={props.onAction}
          />
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
          {props.trailing}
        </div>
      </div>

      <JourneyRibbon state={doc.state} compact={compact} />
    </header>
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

/** Writing → Approved → Building → Done, as a thread drawn up to where the document is. The red
 *  thread (brand madder) grows to the current stop when the state changes; a building document's
 *  stop pulses. */
export function JourneyRibbon({ state, compact }: { state: DocState; compact?: boolean }) {
  const at = journeyIndex(state)
  const span = JOURNEY.length - 1
  const thread = useThreadDraw()
  return (
    <ol className="aw-sp-journey" data-compact={compact ? 'true' : 'false'} aria-label={`Journey: ${STATE_LABEL[state]}`} style={{ '--at': at / span } as React.CSSProperties}>
      <span className="aw-sp-journey-track" aria-hidden="true">
        <span className="aw-sp-journey-thread" ref={thread} />
      </span>
      {JOURNEY.map((stop, i) => (
        <li
          key={stop.key}
          className="aw-sp-journey-stop"
          data-reached={i < at || (i === at && state === 'archived') ? 'done' : i === at ? 'current' : 'ahead'}
          data-live={i === at && state === 'building' ? 'true' : undefined}
          aria-current={i === at ? 'step' : undefined}
        >
          <span className="aw-sp-journey-knot" aria-hidden="true">
            {i < at || (i === at && state === 'archived') ? <Icon name="check" size={9} weight={700} /> : null}
          </span>
          <span className="aw-sp-journey-label">
            {stop.label}
            {i === at && state === 'ready' ? <span className="aw-sp-journey-sub"> · ready</span> : null}
          </span>
        </li>
      ))}
    </ol>
  )
}

/** The thread draws in from the left when the ribbon first appears; later state changes slide it
 *  (a CSS transition). */
function useThreadDraw() {
  const ref = React.useRef<HTMLSpanElement>(null)
  React.useLayoutEffect(() => {
    const el = ref.current
    if (!el || typeof el.animate !== 'function' || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    const animation = el.animate([{ transform: 'scaleX(0)' }], { duration: 600, easing: 'cubic-bezier(0.16, 1, 0.3, 1)', delay: 80 })
    return () => animation.cancel()
  }, [])
  return ref
}
