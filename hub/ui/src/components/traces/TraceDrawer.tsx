import type * as React from 'react'
import { useRef, useState, type CSSProperties } from 'react'
import { useRunTrace, useTrace } from '@/api/traces'
import { Icon } from '@/components/common/Icon'
import { Drawer } from '@/components/layout/Drawer'
import { TraceView } from '@/components/traces/TraceView'

const DRAWER_WIDTH = 920

/** Reads a trace by run or by trace id; only one of the two queries is ever enabled. Mounted
 *  only while the drawer is open, so a closed affordance costs no request. */
export function TraceDrawerBody({ runId, traceId }: { runId?: string; traceId?: string }) {
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
    <div
      data-testid="trace-detail"
      className="min-h-0 flex-1"
      data-run-id={runId ?? ''} data-trace-id={traceId ?? ''}>
      <TraceView
        detail={runId ? runData : idData}
        isLoading={runId ? runLoading : idLoading}
        error={runId ? runError : idError}
        offset={offset}
        onOffsetChange={setOffset}
      />
    </div>
  )
}

/** The trace drawer, opened and closed by its caller (a list that opens a row's trace). */
export function TraceDrawerPanel({
  runId,
  traceId,
  open,
  onOpenChange,
  header,
  triggerRef: givenTriggerRef,
}: {
  runId?: string
  traceId?: string
  open: boolean
  onOpenChange: (open: boolean) => void
  /** A line above the trace (the build view puts the run's name and its conversation link there). */
  header?: React.ReactNode
  /** The control focus returns to when the drawer closes. */
  triggerRef?: React.RefObject<HTMLButtonElement | null>
}) {
  const ownTriggerRef = useRef<HTMLButtonElement>(null)
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="Trace"
      side="right"
      width={DRAWER_WIDTH}
      triggerRef={givenTriggerRef ?? ownTriggerRef}
    >
      <div className="flex h-full min-h-0 flex-col" data-testid="trace-drawer-column">
        {open && header ? <div className="aw-trace-drawer-header shrink-0">{header}</div> : null}
        {open && <TraceDrawerBody key={runId ?? traceId} runId={runId} traceId={traceId} />}
      </div>
    </Drawer>
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
        <div className="flex h-full min-h-0 flex-col" data-testid="trace-drawer-column">
          {open && <TraceDrawerBody runId={runId} traceId={traceId} />}
        </div>
      </Drawer>
      </span>
    </>
  )
}
