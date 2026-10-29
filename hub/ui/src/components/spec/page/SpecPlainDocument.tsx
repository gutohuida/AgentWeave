import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { toast } from '@/lib/toast'
import '@/styles/spec-page.css'

/** What a document with no structure the page can draw says: its path and phase, and its text,
 *  read only (the overview, a file found on disk). Never script and never markup: the text alone. */
export interface PlainDocument {
  path: string
  phase: string | null
  text: string
}

export function SpecPlainDocument({ plain, message }: { plain: PlainDocument | null; message: string }) {
  if (!plain) return <EmptyState icon="article" title="This document cannot be drawn" description={message} />
  return (
    <div className="aw-sp-plain" data-testid="spec-plain-document">
      <div className="aw-sp-plain-head">
        <Icon name="article" size={15} />
        <span className="aw-sp-plain-path" title={plain.path}>
          {plain.path}
        </span>
        {plain.phase ? <span className="aw-sp-phase">{plain.phase}</span> : null}
        <Button
          variant="ghost"
          size="xs"
          onClick={() => {
            void navigator.clipboard?.writeText(plain.path)
            toast({ title: 'Path copied', tone: 'success' })
          }}
        >
          Copy path
        </Button>
      </div>
      <p className="aw-sp-plain-note">{message} Its text, read only:</p>
      <div className="aw-sp-plain-text">{plain.text}</div>
    </div>
  )
}
