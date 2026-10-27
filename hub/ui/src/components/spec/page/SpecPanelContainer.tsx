import * as React from 'react'
import { LoadingThread } from '@/components/common/LoadingThread'
import { SpecPlainDocument } from './SpecPlainDocument'
import { Icon } from '@/components/common/Icon'
import { SpecDocumentFacts } from './SpecDocumentFacts'
import { SpecAdoptButton } from '../SpecAdoptButton'
import { SpecCorpusStrip } from '../SpecCorpusStrip'
import { useBuildProgress, useSpecListData, useSpecSurface, type SpecSurfaceHost } from './useSpecSurface'
import { SpecOpenPicker } from './SpecOpenPicker'
import { SpecSidePanel } from './SpecWorkspace'
import type { SpecListEntry } from './model'
import type { LoopSummary } from '@/api/loops'

/** The conversation's spec panel for one document: the redesigned page in one column. */
export function SpecPanelContainer(props: {
  path: string
  onOpenDocument: (path: string) => void
  onOpenTasks?: (taskIds: string[]) => void
  onOpenLoop?: (loop: LoopSummary) => void
  onDeleted?: () => void
  /** The document this conversation is attached to, for the switcher's shortcuts. */
  attachedPath?: string | null
  /** Documents opened lately (the panel's open tabs), most recent first. */
  recent?: string[]
  onNew?: () => void
  onClose?: () => void
}) {
  return <PanelFor key={props.path} {...props} />
}

function PanelFor(props: React.ComponentProps<typeof SpecPanelContainer>) {
  const host: SpecSurfaceHost = {
    onOpenDocument: props.onOpenDocument,
    onOpenTasks: props.onOpenTasks,
    onOpenLoop: props.onOpenLoop,
    onDeleted: props.onDeleted ?? props.onClose,
  }
  const result = useSpecSurface(props.path, host)
  const list = useSpecListData()
  const progress = useBuildProgress()
  if (result.status !== 'ready') {
    // Nothing to draw yet (loading) or ever (a document without structure): still the panel, still
    // closable, and still saying what is wrong with the corpus around it.
    return (
      <div className="aw-sp aw-sp-panel h-full min-h-0" data-layout="panel" data-testid="spec-document-panel">
        <div className="aw-sp-main">
          <div data-testid="spec-document-header" />
          {props.onClose ? (
            <div className="aw-sp-banner" style={{ alignItems: 'flex-end' }}>
              <button data-slot="icon-button" type="button" className="aw-icon-button" data-testid="spec-document-close" onClick={props.onClose} aria-label="Close document" title="Close document">
                <Icon name="close" size={15} />
              </button>
            </div>
          ) : null}
          {result.status === 'loading' ? (
            <LoadingThread label="Loading specification document" minHeight={240} />
          ) : (
            <SpecPlainDocument plain={result.plain} message={result.message} />
          )}
          <div className="aw-sp-banner">
            <SpecDocumentFacts path={props.path} specList={list.specList} onOpenTasks={props.onOpenTasks} onOpenRequirement={() => undefined} />
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="h-full min-h-0" data-testid="spec-document-panel">
      <SpecSidePanel
        {...result.surface}
        onClose={props.onClose}
        list={{
          entries: list.entries,
          prefs: list.prefs,
          onPrefsChange: list.setPrefs,
          onNew: props.onNew ?? (() => undefined),
          attachedPath: props.attachedPath,
          recent: props.recent,
          progress,
        }}
      />
    </div>
  )
}

/** Choosing a spec to open (the Specs tab, the Ctrl/Cmd+K dialog): the one picker, fed by the Hub.
 *  Opening is for reading; attaching stays the composer's control. */
export function SpecPickerContainer(props: {
  onOpen: (path: string) => void
  onNew: () => void
  attachedPath?: string | null
  openPath?: string | null
  recent?: string[]
  autoFocus?: boolean
}) {
  const list = useSpecListData()
  const progress = useBuildProgress()
  const [adopted, setAdopted] = React.useState(false)
  const now = React.useMemo(() => new Date(), [])
  return (
    <div className="aw-sp aw-sp-panel" data-layout="panel" data-testid="spec-picker">
      {list.specList ? <SpecCorpusStrip specList={list.specList} adoptedSinceRebuild={adopted} onRebuilt={() => setAdopted(false)} /> : null}
      <SpecOpenPicker
        entries={list.entries}
        prefs={list.prefs}
        onPrefsChange={list.setPrefs}
        onOpen={props.onOpen}
        onNew={props.onNew}
        now={now}
        attachedPath={props.attachedPath}
        openPath={props.openPath}
        recent={props.recent}
        progress={progress}
        autoFocus={props.autoFocus}
        rowAction={(entry: SpecListEntry) => (entry.untracked ? <SpecAdoptButton path={entry.path} onAdopted={() => setAdopted(true)} /> : null)}
      />
    </div>
  )
}
