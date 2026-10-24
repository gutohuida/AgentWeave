import { readableApiError } from '@/api/client'
import { useWeaveThread } from '@/api/manager'
import { Button } from '@/components/ui/button'
import '@/styles/thread.css'

/** "Weave the thread": asks the chapters job to fire now. The Thread page draws it only while the
 *  job is on; the Hub answers 409 if it has no runner, which is said here rather than hidden. */
export function WeaveButton() {
  const weave = useWeaveThread()
  return (
    <div className="aw-thread-weave">
      {weave.error ? (
        <span role="alert" className="aw-knot-meta">
          {readableApiError(weave.error, 'The thread could not be woven.')}
        </span>
      ) : weave.isSuccess ? (
        <span role="status" className="aw-knot-meta">
          Weaving the thread. Reload this page once it finishes to see the new chapters.
        </span>
      ) : null}
      <Button variant="outline" data-slot="weave-thread" disabled={weave.isPending} onClick={() => weave.mutate()}>
        Weave the thread
      </Button>
    </div>
  )
}
