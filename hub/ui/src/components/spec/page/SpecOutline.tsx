import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Icon } from '@/components/common/Icon'
import { anchors, EVIDENCE_LABEL, EVIDENCE_TONE, TASK_STATUS_LABEL, type BuildView, type CheckFinding, type SpecDocumentView } from './model'
import '@/styles/spec-page.css'

interface OutlineItem {
  anchor: string
  label: string
  detail?: string
  /** A coloured dot: evidence state, task status. */
  tone?: string
  toneLabel?: string
  marker?: 'blocking' | 'warning'
}

interface OutlineGroup {
  title: string
  items: OutlineItem[]
}

function outlineOf(doc: SpecDocumentView, findings: CheckFinding[], builds: BuildView[]): OutlineGroup[] {
  const marker = (kind: CheckFinding['target']['kind'], id: string): OutlineItem['marker'] => {
    const hits = findings.filter((f) => f.target.kind === kind && f.target.id === id)
    return hits.some((f) => f.severity === 'blocking') ? 'blocking' : hits.length ? 'warning' : undefined
  }
  const sections: OutlineItem[] = [
    { anchor: anchors.section('summary'), label: 'Summary', marker: marker('section', 'summary') },
    { anchor: anchors.section('problem'), label: 'Problem', marker: marker('section', 'problem') },
    { anchor: anchors.section('scope'), label: 'Scope', marker: marker('section', 'scope') },
    ...(doc.slices?.length ? [{ anchor: anchors.section('slices'), label: 'Slices', detail: String(doc.slices.length) }] : []),
    { anchor: anchors.section('requirements'), label: 'Requirements', detail: String(doc.requirements.length) },
    { anchor: anchors.section('tasks'), label: 'Tasks', detail: String(doc.tasks.length) },
    { anchor: anchors.section('builds'), label: 'Builds', detail: builds.length ? String(builds.length) : undefined },
    ...(doc.openQuestions.length ? [{ anchor: anchors.section('questions'), label: 'Open questions' }] : []),
  ]
  return [
    { title: 'Sections', items: sections },
    {
      title: 'Requirements',
      items: doc.requirements.map((r) => ({
        anchor: anchors.requirement(r.identifier),
        label: r.identifier,
        detail: r.key.replace(/-/g, ' '),
        tone: EVIDENCE_TONE[r.evidence],
        toneLabel: EVIDENCE_LABEL[r.evidence],
        marker: marker('requirement', r.identifier),
      })),
    },
    {
      title: 'Tasks',
      items: doc.tasks.map((t) => ({
        anchor: anchors.task(t.key),
        label: t.title,
        tone: `var(--sp-status-${t.status ?? 'pending'})`,
        toneLabel: TASK_STATUS_LABEL[t.status ?? 'pending'],
        marker: marker('task', t.key),
      })),
    },
  ]
}

/** The open document's outline (FR-6): sections, requirements with their evidence, tasks with their
 *  status; check findings marked. Picking an entry jumps there; the entry in view is highlighted. */
export function SpecOutlineRail({
  doc,
  findings,
  builds,
  active,
  onJump,
}: {
  doc: SpecDocumentView
  findings: CheckFinding[]
  builds: BuildView[]
  active: string | null
  onJump: (anchor: string) => void
}) {
  const groups = outlineOf(doc, findings, builds)
  const activeRef = React.useRef<HTMLButtonElement>(null)
  // Keep the highlighted entry in the rail's own view. Not scrollIntoView: that also scrolls the
  // document the rail sits in, and cancels a jump in flight.
  React.useEffect(() => {
    const item = activeRef.current
    const rail = item?.closest<HTMLElement>('.aw-sp-rail')
    if (!item || !rail) return
    const top = item.offsetTop - rail.offsetTop
    if (top < rail.scrollTop + 8) rail.scrollTop = top - 8
    else if (top + item.offsetHeight > rail.scrollTop + rail.clientHeight - 8) rail.scrollTop = top + item.offsetHeight - rail.clientHeight + 8
  }, [active])
  return (
    <nav className="aw-sp-outline" aria-label="Outline">
      {groups.map((g) => (
        <div key={g.title} className="aw-sp-outline-group">
          <div className="aw-sp-outline-title">{g.title}</div>
          <ul>
            {g.items.map((item) => (
              <li key={item.anchor}>
                <button
                  data-slot="outline-item"
                  type="button"
                  ref={item.anchor === active ? activeRef : undefined}
                  className="aw-sp-outline-item"
                  data-active={item.anchor === active ? 'true' : 'false'}
                  data-kind={g.title}
                  onClick={() => onJump(item.anchor)}
                  title={item.toneLabel ? `${item.label}: ${item.toneLabel}` : item.label}
                >
                  {item.tone ? <span className="aw-sp-outline-dot" style={{ background: item.tone }} /> : null}
                  <span className="aw-sp-outline-label">{item.label}</span>
                  {item.detail && g.title === 'Requirements' ? <span className="aw-sp-outline-detail">{item.detail}</span> : null}
                  {item.marker ? <span className="aw-sp-outline-marker" data-severity={item.marker} aria-label={item.marker === 'blocking' ? 'Blocks approval' : 'Warning'} /> : null}
                  {item.detail && g.title !== 'Requirements' ? <span className="aw-sp-outline-count">{item.detail}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

/** The same outline as a menu, for the panel where there is no room for a rail. */
export function SpecOutlineMenu({
  doc,
  findings,
  builds,
  active,
  onJump,
}: {
  doc: SpecDocumentView
  findings: CheckFinding[]
  builds: BuildView[]
  active: string | null
  onJump: (anchor: string) => void
}) {
  const groups = outlineOf(doc, findings, builds)
  const marked = groups.some((g) => g.items.some((i) => i.marker))
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button data-slot="icon-button" type="button" className="aw-icon-button aw-sp-outline-trigger" aria-label="Outline" title="Outline">
          <Icon name="list_tree" size={15} />
          {marked ? <span className="aw-sp-outline-marker" data-severity="blocking" /> : null}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} collisionPadding={12} className="aw-menu aw-pop aw-sp-outline-menu">
          {groups.map((g, gi) => (
            <React.Fragment key={g.title}>
              {gi ? <DropdownMenu.Separator className="aw-menu-separator" /> : null}
              <DropdownMenu.Label className="aw-menu-label">{g.title}</DropdownMenu.Label>
              {g.items.map((item) => (
                <DropdownMenu.Item key={item.anchor} className="aw-menu-item" data-current={item.anchor === active ? 'true' : undefined} onSelect={() => onJump(item.anchor)}>
                  <span className="aw-menu-item-icon">{item.tone ? <span className="aw-sp-outline-dot" style={{ background: item.tone }} /> : null}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {item.label}
                    {item.detail && g.title === 'Requirements' ? <span className="aw-sp-outline-detail"> {item.detail}</span> : null}
                  </span>
                  {item.marker ? <span className="aw-sp-outline-marker" data-severity={item.marker} /> : null}
                </DropdownMenu.Item>
              ))}
            </React.Fragment>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
