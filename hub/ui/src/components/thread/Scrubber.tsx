import { Icon } from '@/components/common/Icon'
import '@/styles/thread.css'

interface ScrubberProps {
  /** The oldest surface knot is the first in the list. */
  atBeginning: boolean
  /** The view is at the present end. */
  atPresent: boolean
  onJumpToBeginning: () => void
  onBackToPresent: () => void
}

/** The two controls that cross the whole history in one action. */
export function Scrubber({ atBeginning, atPresent, onJumpToBeginning, onBackToPresent }: ScrubberProps) {
  return (
    <div className="aw-thread-scrubber" role="group" aria-label="Move along the thread">
      <button type="button" data-slot="thread-scrub" className="aw-thread-scrub" onClick={onJumpToBeginning} disabled={atBeginning}>
        <Icon name="arrow_upward" size={14} />
        Jump to the beginning
      </button>
      <button type="button" data-slot="thread-scrub" className="aw-thread-scrub" onClick={onBackToPresent} disabled={atPresent}>
        <Icon name="arrow_downward" size={14} />
        Back to the present
      </button>
    </div>
  )
}
