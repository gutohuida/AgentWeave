import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { useActiveAnchor, useDocumentNavigation, useEnterChildren } from './hooks'
import { anchors, type BuildView, type CheckFinding, type CheckState, type DocumentFilters, type ListPreferences, type SpecAction, type SpecDocumentView, type SpecListEntry } from './model'
import { SpecBuildsSection } from './SpecBuilds'
import { SpecDocList, SpecDocSwitcher } from './SpecDocList'
import { SpecDocumentBody, type BodyPart } from './SpecDocumentBody'
import { SpecOutlineMenu, SpecOutlineRail } from './SpecOutline'
import { SpecPageHeader, type HeaderChrome } from './SpecPageHeader'
import { SpecPanelDocSwitcher, SpecPanelNav, type PanelListProps } from './SpecPanelNav'
import { Segmented } from '@/components/ui/segmented'
import '@/styles/spec-page.css'

/** Everything both layouts of the page need: the document, its builds and check, the list, and
 *  the callbacks a container answers. */
export interface SpecSurfaceProps {
  doc: SpecDocumentView
  builds: BuildView[]
  check: CheckState
  filters: DocumentFilters
  onFiltersChange: (next: DocumentFilters) => void
  now: Date
  /** The position a link named, opened on arrival. */
  initialAnchor?: string | null
  onAction: (action: SpecAction) => void
  onOpenDocument: (path: string) => void
  onCopyLink: (anchor: string | null) => void
  onCopyPath: () => void
  onArchive?: () => void
  onDelete?: () => void
  onStartBuild: () => void
  onOpenRuns: (build: BuildView) => void
  onStopBuild: (build: BuildView) => void
  /** Under the header, above the document: what the operator has to decide (amendments, proposals), what the actions said (refusals, gaps) and the dialogs. */
  /** Decisions the Hub's phase controls offer beyond the page's own buttons. */
  chrome?: HeaderChrome
  banner?: (context: { jump: (anchor: string) => void }) => React.ReactNode
}

export interface SpecWorkspaceProps extends SpecSurfaceProps {
  entries: SpecListEntry[]
  listPrefs: ListPreferences
  onListPrefsChange: (next: ListPreferences) => void
  onNew: () => void
  /** The document list as a left column, or as a switcher above a full-width document. */
  layout: 'column' | 'switcher'
  /** Pinned under the list (the evidence entry, the defects report). */
  listFooter?: React.ReactNode
}

function useSurface(props: SpecSurfaceProps, scroller: React.RefObject<HTMLDivElement | null>) {
  const nav = useDocumentNavigation(scroller, props.initialAnchor ?? null)
  const findings: CheckFinding[] = props.check.status === 'done' ? props.check.findings : []
  const running = props.builds.find((b) => b.running) ?? null
  const firstFinding = findings[0]
  const findingAnchor = firstFinding
    ? firstFinding.target.kind === 'requirement'
      ? anchors.requirement(firstFinding.target.id)
      : firstFinding.target.kind === 'task'
        ? anchors.task(firstFinding.target.id)
        : anchors.section(firstFinding.target.id)
    : null
  const onAction = (action: SpecAction) => (action === 'open-build' && running ? nav.jump(anchors.build(running.id)) : props.onAction(action))
  return { nav, findings, running, findingAnchor, onAction }
}

/** The Spec tab: the document list, the document with its outline, and its header. */
export function SpecWorkspace(props: SpecWorkspaceProps) {
  const scroller = React.useRef<HTMLDivElement>(null)
  const { nav, findings, running, findingAnchor, onAction } = useSurface(props, scroller)
  const active = useActiveAnchor(scroller, [props.doc.path])
  const content = React.useRef<HTMLDivElement>(null)
  useEnterChildren(content, props.doc.path)
  const { doc } = props

  const list = (variant: 'column' | 'popover') => (
    <SpecDocList
      entries={props.entries}
      active={doc.path}
      prefs={props.listPrefs}
      onPrefsChange={props.onListPrefsChange}
      onOpen={props.onOpenDocument}
      onNew={props.onNew}
      now={props.now}
      variant={variant}
      footer={props.listFooter}
    />
  )

  return (
    <div className="aw-sp" data-layout={props.layout}>
      {props.layout === 'column' ? list('column') : null}
      <div className="aw-sp-main">
        <SpecPageHeader
          chrome={props.chrome}
          doc={doc}
          check={props.check}
          runningBuild={running?.number ?? null}
          now={props.now}
          leading={props.layout === 'switcher' ? <SpecDocSwitcher title={doc.title}>{list('popover')}</SpecDocSwitcher> : null}
          trailing={
            <span className="aw-sp-outline-menu-slot">
              <SpecOutlineMenu doc={doc} findings={findings} builds={props.builds} active={active} onJump={nav.jump} />
            </span>
          }
          canBack={nav.canBack}
          canForward={nav.canForward}
          onBack={nav.back}
          onForward={nav.forward}
          onAction={onAction}
          onJumpToFindings={() => findingAnchor && nav.jump(findingAnchor)}
          onOpenDocument={props.onOpenDocument}
          onCopyLink={() => props.onCopyLink(null)}
          onCopyPath={props.onCopyPath}
          onArchive={props.onArchive}
          onDelete={props.onDelete}
        />
        {props.banner?.({ jump: nav.jump })}
        <div className="aw-sp-scroll" ref={scroller}>
          <div className="aw-sp-columns">
            <div className="aw-sp-content" key={doc.path} ref={content}>
              <SpecDocumentBody
                doc={doc}
                filters={props.filters}
                onFiltersChange={props.onFiltersChange}
                findings={findings}
                parts={['document', 'tasks', 'builds']}
                flash={nav.flash}
                onJump={nav.jump}
                onCopyLink={props.onCopyLink}
                onOpenDocument={props.onOpenDocument}
                builds={
                  <SpecBuildsSection
                    builds={props.builds}
                    canBuild={doc.state === 'approved' && doc.kind === 'change-spec'}
                    now={props.now}
                    flash={nav.flash}
                    onStartBuild={props.onStartBuild}
                    onOpenRuns={props.onOpenRuns}
                    onStop={props.onStopBuild}
                    onCopyLink={props.onCopyLink}
                  />
                }
              />
            </div>
            <div className="aw-sp-rail">
              <SpecOutlineRail doc={doc} findings={findings} builds={props.builds} active={active} onJump={nav.jump} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

type PanelTab = 'document' | 'tasks' | 'builds'

function tabFor(anchor: string): PanelTab {
  if (anchor.startsWith('task-') || anchor === anchors.section('tasks')) return 'tasks'
  if (anchor.startsWith('build-') || anchor === anchors.section('builds')) return 'builds'
  return 'document'
}

/** The conversation's spec panel (FR-8): the same header, actions, document, filters and builds, in
 *  one column. The outline is a menu, and the document, its tasks and its builds are tabs. */
export function SpecSidePanel(props: SpecSurfaceProps & { onClose?: () => void; list?: PanelListProps }) {
  const scroller = React.useRef<HTMLDivElement>(null)
  const [tab, setTab] = React.useState<PanelTab>(() => (props.initialAnchor ? tabFor(props.initialAnchor) : 'document'))
  const { nav, findings, running, findingAnchor, onAction } = useSurface(props, scroller)
  const active = useActiveAnchor(scroller, [props.doc.path, tab])
  const content = React.useRef<HTMLDivElement>(null)
  useEnterChildren(content, `${props.doc.path}:${tab}`)
  const jump = (anchor: string) => {
    setTab(tabFor(anchor))
    nav.jump(anchor)
  }
  // Back and forward can land on a position in another tab.
  const position = nav.current
  React.useEffect(() => {
    if (position) setTab(tabFor(position))
  }, [position])
  const { doc } = props
  const parts: BodyPart[] = [tab]
  const findingsIn = (t: PanelTab) =>
    findings.filter((f) => (t === 'tasks' ? f.target.kind === 'task' : t === 'document' ? f.target.kind !== 'task' : false)).length

  return (
    <div className="aw-sp aw-sp-panel" data-layout="panel">
      <div className="aw-sp-main">
        <SpecPageHeader
          chrome={props.chrome}
          doc={doc}
          check={props.check}
          runningBuild={running?.number ?? null}
          now={props.now}
          compact
          trailing={
            <>
              <SpecOutlineMenu doc={doc} findings={findings} builds={props.builds} active={active} onJump={jump} />
              {props.onClose ? (
                <button data-slot="icon-button" type="button" className="aw-icon-button" data-testid="spec-document-close" onClick={props.onClose} aria-label="Close document" title="Close document">
                  <Icon name="close" size={15} />
                </button>
              ) : null}
            </>
          }
          canBack={nav.canBack}
          canForward={nav.canForward}
          onBack={nav.back}
          onForward={nav.forward}
          onAction={(a) => (a === 'open-build' && running ? jump(anchors.build(running.id)) : onAction(a))}
          onJumpToFindings={() => findingAnchor && jump(findingAnchor)}
          onOpenDocument={props.onOpenDocument}
          onCopyLink={() => props.onCopyLink(null)}
          onCopyPath={props.onCopyPath}
          onArchive={props.onArchive}
          onDelete={props.onDelete}
        />
        {props.banner?.({ jump })}
        {props.list ? <SpecPanelDocSwitcher doc={doc} list={props.list} onOpenDocument={props.onOpenDocument} now={props.now} /> : null}
        <div className="aw-sp-panel-tabs">
          <Segmented<PanelTab>
            label="Show"
            value={tab}
            onChange={setTab}
            options={[
              { value: 'document', label: 'Document', count: findingsIn('document') || undefined },
              { value: 'tasks', label: 'Tasks', count: doc.tasks.length },
              { value: 'builds', label: running ? (
                  <>
                    Builds
                    <span className="aw-sp-live" aria-label="A build is running" />
                  </>
                ) : (
                  'Builds'
                ), count: props.builds.length || undefined },
            ]}
          />
        </div>
        <SpecPanelNav
          doc={doc}
          tab={tab}
          filters={props.filters}
          onFiltersChange={props.onFiltersChange}
          active={active}
          onJump={jump}
        />
        <div className="aw-sp-scroll" ref={scroller}>
          <div className="aw-sp-content" key={`${doc.path}:${tab}`} ref={content}>
            <SpecDocumentBody
              doc={doc}
              filters={props.filters}
              onFiltersChange={props.onFiltersChange}
              findings={findings}
              parts={parts}
              compact
              hideFilterBar
              flash={nav.flash}
              onJump={jump}
              onCopyLink={props.onCopyLink}
              onOpenDocument={props.onOpenDocument}
              builds={
                <SpecBuildsSection
                  builds={props.builds}
                  canBuild={doc.state === 'approved' && doc.kind === 'change-spec'}
                  now={props.now}
                  flash={nav.flash}
                  onStartBuild={props.onStartBuild}
                  onOpenRuns={props.onOpenRuns}
                  onStop={props.onStopBuild}
                  onCopyLink={props.onCopyLink}
                />
              }
            />
          </div>
        </div>
      </div>
    </div>
  )
}
