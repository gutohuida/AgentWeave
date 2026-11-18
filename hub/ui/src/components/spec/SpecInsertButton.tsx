import { Icon } from '@/components/common/Icon'
import type { SpecReference } from '@/lib/specReference'

/** Puts a box for a spec in the conversation's composer. A button of its own, beside the row or
 *  header that opens the spec, so inserting never opens and opening never inserts. */
export function SpecInsertButton({
  spec,
  onInsert,
  header = false,
}: {
  spec: SpecReference
  onInsert: (spec: SpecReference) => void
  header?: boolean
}) {
  const label = `Insert ${spec.title} into the message`
  return (
    <button
      data-slot="icon-button"
      type="button"
      className="aw-icon-button"
      data-testid={header ? 'spec-insert-header' : 'spec-insert-row'}
      data-id={spec.id}
      aria-label={label}
      title={label}
      // The composer keeps its caret: a press must not take focus from it before the insert reads it.
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => onInsert(spec)}
    >
      <Icon name="mention" size={14} />
    </button>
  )
}
