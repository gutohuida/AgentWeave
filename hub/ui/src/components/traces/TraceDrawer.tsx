import { useRef, useState, type CSSProperties } from 'react'
import { useRunTrace, useTrace } from '@/api/traces'
import { Icon } from '@/components/common/Icon'
import { Drawer } from '@/components/layout/Drawer'
import { TraceView } from '@/components/traces/TraceView'

const DRAWER_WIDTH = 920

/** Reads a trace by run or by trace id; only one of the two queries is ever enabled. Mounted
 *  only while the drawer is open, so a closed affordance costs no request. */
function TraceDrawerBody({ runId, traceId }: { runId?: string; traceId?: string }) {
  const [offset, setOffset] = useState(0)
  const { data: runData, isLoading: runLoading, error: runError } = useRunTrace(
    runId ?? null,
    offset,
  )
  const { data: idData, isLoading: idLoading, error: idError } = useTrace(
    runId ? null : traceId ?? null,
    offset,
  )
  return (
    <TraceView
      detail={runId ? runData : idData}
      isLoading={runId ? runLoading : idLoading}
      error={runId ? runError : idError}
      offset={offset}
      onOffsetChange={setOffset}
    />
  )
}

/**
 * A small "Trace" control that opens a run's trace in a drawer. Self-contained — it owns its open
 * state, the focus return, and the query — so a run anywhere in the app gets one with one line.
 */
export function TraceButton({
  runId,
  traceId,
  label = 'Trace',
  title = 'Open this run’s trace',
  className,
  style,
  testId,
}: {
  runId?: string
  traceId?: string
  label?: string
  title?: string
  className?: string
  style?: CSSProperties
  testId?: string
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  if (!runId && !traceId) return null
  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={className ?? 'aw-link aw-link-inline inline-flex items-center gap-1'}
        title={title}
        style={style}
        data-testid={testId}
        onClick={(event) => {
          event.stopPropagation()
          setOpen(true)
        }}
      >
        <Icon name="monitoring" size={12} />
        {label}
      </button>
      {/* The drawer is portalled, but React still bubbles its events through this tree: without
          this, a click inside the trace would reach whatever row the button sits in. */}
      <span style={{ display: 'contents' }} onClick={(event) => event.stopPropagation()}>
      <Drawer
        open={open}
        onOpenChange={setOpen}
        title="Trace"
        side="right"
        width={DRAWER_WIDTH}
        triggerRef={triggerRef}
      >
        {open && <TraceDrawerBody runId={runId} traceId={traceId} />}
      </Drawer>
      </span>
    </>
  )
}
