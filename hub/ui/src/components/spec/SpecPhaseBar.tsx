import type { LoopSummary } from '@/api/loops'
import { toast } from '@/lib/toast'
import { SpecDocumentHeader } from './SpecDocumentHeader'
import { useSpecPhaseControls, type SpecPhaseControls } from './useSpecPhaseControls'

/**
 * The document's phase and decisions, standing alone: the header without the health line, for a
 * host that shows the document's facts elsewhere (and for the tests of the decisions themselves).
 * `SpecDocumentPanel` composes the same controls with the health line and its tools.
 */
export function SpecPhaseBar({
  path,
  onOpenLoop,
  onDeleted,
}: {
  path: string
  /** Called once the Hub has deleted this document (F829). The host leaves it: nothing on this
   *  page can show a document that no longer exists. */
  onDeleted?: () => void
  /** Opens a loop's tab. Each host supplies its own: the conversation panel opens the tab beside
   *  the document; the Spec destination has no panel shell and must navigate to one. Without it
   *  the flow's label is text rather than a link that does nothing. */
  onOpenLoop?: (loop: LoopSummary) => void
}) {
  const controls = useSpecPhaseControls(path, onOpenLoop, onDeleted)
  if (!controls) return null
  return <SpecPhaseHeader path={path} controls={controls} health={null} />
}

/** `SpecDocumentHeader` fed from `useSpecPhaseControls`. */
export function SpecPhaseHeader({
  path,
  controls,
  health,
  tools,
  badges,
  onOpenLocation,
}: {
  path: string
  controls: SpecPhaseControls
  health: React.ReactNode
  tools?: React.ReactNode
  /** Beside the phase, after the controls' own (an archived marker, Place under…). */
  badges?: React.ReactNode
  onOpenLocation?: () => void
}) {
  const { document } = controls
  return (
    <>
      <SpecDocumentHeader
        path={path}
        title={document.title}
        kind={document.kind}
        phase={document.phase}
        rigor={controls.rigorChoice.value}
        rigorChoice={controls.rigorChoice}
        primary={controls.primary}
        beforePrimary={controls.beforePrimary}
        menu={controls.menu}
        onReopen={controls.reopen}
        onArchive={controls.archive}
        onDelete={controls.remove}
        onCopyPath={() => {
          void navigator.clipboard?.writeText(path)
          toast({ title: 'Path copied', tone: 'success' })
        }}
        badges={
          <>
            {controls.badges}
            {badges}
          </>
        }
        tools={tools}
        health={health}
        messages={controls.messages}
        onOpenLocation={onOpenLocation}
      />
      {controls.dialogs}
    </>
  )
}
