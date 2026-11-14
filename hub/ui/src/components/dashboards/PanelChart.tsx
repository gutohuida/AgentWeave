import * as React from 'react'
import type { CellValue, PanelRun } from '@/api/dashboards'
import '@/styles/dashboards.css'

/**
 * What one dashboard panel draws (`ask-any-agent-for-a-dashboard-and-get-one-that-stays`, FR-10,
 * FR-12, FR-15): the query's error, the warning saying why its result cannot be drawn as its kind,
 * or the chart. Drawn here with SVG and CSS rather than a charting library: five kinds over a
 * handful of rows need no scales or zoom, and every colour and size below is the app's own
 * variable, so both themes follow with nothing to configure. The motion (draw-in, values that
 * slide on a refresh or an edit, hover lift and tooltip) is CSS in styles/dashboards.css, and
 * stops when the system asks for reduced motion.
 *
 * The label column is the first; every later numeric column is a series. That is the same rule
 * `drawing_warning` in `hub/hub/api/v1/dashboards.py` uses to decide a result cannot be drawn.
 */

/** The app's agent palette, validated for both themes; series take them in order. */
const SERIES = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => `var(--agent-${n})`)

const isNumber = (v: CellValue): v is number => typeof v === 'number' && Number.isFinite(v)

const compact = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })
const formatNumber = (v: number) => compact.format(v)

interface Series {
  name: string
  color: string
  values: number[]
}

/** The label column and the numeric columns after it, as the bar and line kinds draw them. */
function seriesOf(panel: PanelRun): { labels: string[]; series: Series[] } {
  const labels = panel.rows.map((row) => String(row[0] ?? ''))
  const series: Series[] = []
  for (let c = 1; c < panel.columns.length; c++) {
    const column = panel.rows.map((row) => row[c])
    if (!column.some(isNumber) || !column.every((v) => v === null || isNumber(v))) continue
    series.push({
      name: panel.columns[c],
      color: SERIES[series.length % SERIES.length],
      values: column.map((v) => (isNumber(v) ? v : 0)),
    })
  }
  return { labels, series }
}

function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null
  return (
    <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs" style={{ color: 'var(--text-2)' }}>
      {series.map((s) => (
        <span key={s.name} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-sm" style={{ background: s.color }} />
          {s.name}
        </span>
      ))}
    </div>
  )
}

const reducedMotion = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** Counts from the value last shown to `target` (from zero on first draw), easing out. */
function useCountUp(target: number, ms = 900): number {
  const [shown, setShown] = React.useState(() => (reducedMotion() ? target : 0))
  const from = React.useRef(shown)
  React.useEffect(() => {
    if (reducedMotion()) {
      from.current = target
      setShown(target)
      return
    }
    const start = performance.now()
    const begin = from.current
    let frame = 0
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      const value = begin + (target - begin) * (1 - Math.pow(1 - t, 3))
      from.current = value
      setShown(value)
      if (t < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, ms])
  return shown
}

interface Tip {
  x: number
  y: number
  label: string
  name: string
  value: number
  color: string
}

type ShowTip = (e: React.MouseEvent, tip: Omit<Tip, 'x' | 'y'>) => void

/** A chart's frame: holds the hovered mark's tooltip, drawn in the app's own surface. */
function ChartFrame({ testId, children }: { testId: string; children: (show: ShowTip, hide: () => void) => React.ReactNode }) {
  const ref = React.useRef<HTMLDivElement>(null)
  const [tip, setTip] = React.useState<Tip | null>(null)
  const show: ShowTip = (e, t) => {
    const box = ref.current?.getBoundingClientRect()
    if (box) setTip({ ...t, x: e.clientX - box.left, y: e.clientY - box.top })
  }
  return (
    <div ref={ref} data-testid={testId} className="aw-dash-chart relative">
      {children(show, () => setTip(null))}
      {tip && (
        <div className="aw-dash-tip" role="tooltip" data-testid="dashboard-tooltip" style={{ left: tip.x, top: tip.y }}>
          <div className="aw-dash-tip-label">{tip.label}</div>
          <div>
            <span className="aw-dash-tip-swatch" style={{ background: tip.color }} />
            {tip.name} <strong className="tabular-nums">{formatNumber(tip.value)}</strong>
          </div>
        </div>
      )}
    </div>
  )
}

/** CSS custom properties and SVG geometry properties, which React's style type does not name. */
const css = (style: Record<string, string | number>) => style as React.CSSProperties

export function NumberChart({ panel }: { panel: PanelRun }) {
  const column = panel.columns.findIndex((_, c) => {
    const values = panel.rows.map((row) => row[c])
    return values.some(isNumber) && values.every((v) => v === null || isNumber(v))
  })
  const value = panel.rows[0]?.[column]
  const numeric = isNumber(value ?? null)
  const target = numeric ? (value as number) : 0
  const counted = useCountUp(target)
  const counting = numeric && counted !== target
  // The element holds the real figure at all times (what a reader, a test or a drive reads); the
  // count is drawn over it while it runs, so nothing ever reads a figure that is mid-count.
  return (
    <div data-testid="chart-number" className="aw-dash-chart relative">
      <div
        data-testid="dashboard-number"
        className="text-4xl font-semibold tabular-nums"
        style={{ color: 'var(--text)', opacity: counting ? 0 : 1 }}
      >
        {numeric ? formatNumber(target) : String(value ?? '—')}
      </div>
      {counting && (
        <div aria-hidden="true" className="absolute left-0 top-0 text-4xl font-semibold tabular-nums" style={{ color: 'var(--text)' }}>
          {formatNumber(Math.round(counted * 100) / 100)}
        </div>
      )}
      <div className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
        {panel.columns[column]}
      </div>
    </div>
  )
}

export function BarChart({ panel, stacked }: { panel: PanelRun; stacked: boolean }) {
  const { labels, series } = seriesOf(panel)
  const totals = labels.map((_, i) => series.reduce((sum, s) => sum + Math.max(0, s.values[i]), 0))
  const max = Math.max(
    1e-9,
    ...(stacked ? totals : series.flatMap((s) => s.values.map((v) => Math.max(0, v)))),
  )
  return (
    <ChartFrame testId={stacked ? 'chart-stacked-bar' : 'chart-bar'}>
      {(show, hide) => (
        <>
          <Legend series={series} />
          <div className="flex flex-col gap-2">
            {labels.map((label, i) => (
              <div key={`${label}-${i}`} className="grid grid-cols-[minmax(6rem,28%)_1fr] items-center gap-3 text-xs">
                <span className="truncate text-right" style={{ color: 'var(--text-2)' }} title={label}>
                  {label}
                </span>
                <div className="flex flex-col gap-1">
                  {stacked ? (
                    <div className="flex h-4 items-center">
                      <svg
                        role="img"
                        aria-label={`${label}: ${series.map((s) => `${s.name} ${formatNumber(s.values[i])}`).join(', ')}`}
                        className="aw-dash-bar h-full"
                        height="100%"
                        style={css({ width: `${(totals[i] / max) * 100}%`, '--j': i })}
                      >
                        {series.map((s, k) => {
                          const before = series.slice(0, k).reduce((sum, o) => sum + Math.max(0, o.values[i]), 0)
                          return (
                            <rect
                              key={s.name}
                              className="aw-dash-mark"
                              height="100%"
                              fill={s.color}
                              style={css({
                                x: `${totals[i] ? (before / totals[i]) * 100 : 0}%`,
                                width: `${totals[i] ? (Math.max(0, s.values[i]) / totals[i]) * 100 : 0}%`,
                              })}
                              onMouseMove={(e) => show(e, { label, name: s.name, value: s.values[i], color: s.color })}
                              onMouseLeave={hide}
                            />
                          )
                        })}
                      </svg>
                      <span className="ml-2 tabular-nums" style={{ color: 'var(--text-3)' }}>
                        {formatNumber(totals[i])}
                      </span>
                    </div>
                  ) : (
                    series.map((s) => (
                      <div key={s.name} className="flex h-4 items-center">
                        <svg
                          role="img"
                          aria-label={`${label} · ${s.name}: ${formatNumber(s.values[i])}`}
                          className="aw-dash-bar h-full"
                          height="100%"
                          style={css({ width: `${(Math.max(0, s.values[i]) / max) * 100}%`, minWidth: s.values[i] > 0 ? 2 : 0, '--j': i })}
                        >
                          <rect
                            className="aw-dash-mark"
                            width="100%"
                            height="100%"
                            rx={2}
                            fill={s.color}
                            onMouseMove={(e) => show(e, { label, name: s.name, value: s.values[i], color: s.color })}
                            onMouseLeave={hide}
                          />
                        </svg>
                        <span className="ml-2 tabular-nums" style={{ color: 'var(--text-3)' }}>
                          {formatNumber(s.values[i])}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </ChartFrame>
  )
}

export function LineChart({ panel }: { panel: PanelRun }) {
  const { labels, series } = seriesOf(panel)
  const W = 560
  const H = 200
  const pad = { l: 44, r: 12, t: 10, b: 28 }
  const all = series.flatMap((s) => s.values)
  const lo = Math.min(0, ...all)
  const hi = Math.max(1e-9, ...all)
  const x = (i: number) => pad.l + (labels.length < 2 ? (W - pad.l - pad.r) / 2 : (i / (labels.length - 1)) * (W - pad.l - pad.r))
  const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b)
  const ticks = [lo, lo + (hi - lo) / 2, hi]
  const every = Math.max(1, Math.ceil(labels.length / 8))
  return (
    <ChartFrame testId="chart-line">
      {(show, hide) => (
        <>
          <Legend series={series} />
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full overflow-visible" role="img" aria-label={panel.title} style={{ fontFamily: 'inherit' }}>
            {ticks.map((t, k) => (
              <g key={k}>
                <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--border-hi)" strokeWidth={1} />
                <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--text-3)">
                  {formatNumber(t)}
                </text>
              </g>
            ))}
            {labels.map((label, i) =>
              i % every === 0 ? (
                <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--text-3)">
                  {label.length > 12 ? `${label.slice(0, 11)}…` : label}
                </text>
              ) : null,
            )}
            {series.map((s) => (
              <g key={s.name}>
                <path
                  className="aw-dash-line"
                  pathLength={1}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  style={css({ d: `path('${s.values.map((v, i) => `${i ? 'L' : 'M'}${x(i)} ${y(v)}`).join(' ')}')` })}
                />
                {s.values.map((v, i) => (
                  <circle
                    key={i}
                    className="aw-dash-dot aw-dash-mark"
                    r={3}
                    fill={s.color}
                    stroke="var(--surface)"
                    strokeWidth={1.5}
                    style={css({ cx: `${x(i)}px`, cy: `${y(v)}px`, '--j': i })}
                    onMouseMove={(e) => show(e, { label: labels[i], name: s.name, value: v, color: s.color })}
                    onMouseLeave={hide}
                  />
                ))}
              </g>
            ))}
          </svg>
        </>
      )}
    </ChartFrame>
  )
}

/** Every value in full (FR-15): cells wrap and break rather than truncate, nothing is masked, and a
 *  long value scrolls with its row instead of being cut. */
export function TableChart({ panel }: { panel: PanelRun }) {
  return (
    <div data-testid="chart-table" className="aw-dash-chart max-h-96 overflow-auto rounded-md" style={{ border: '1px solid var(--border)' }}>
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr style={{ background: 'var(--surface-2)' }}>
            {panel.columns.map((c) => (
              <th key={c} className="sticky top-0 px-3 py-2 font-medium" style={{ color: 'var(--text-2)', background: 'var(--surface-2)' }}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {panel.rows.map((row, r) => (
            <tr key={r} className="aw-dash-row" style={{ borderTop: '1px solid var(--border)' }}>
              {row.map((cell, c) => (
                <td
                  key={c}
                  data-testid="dashboard-table-cell"
                  className={`px-3 py-1.5 align-top ${isNumber(cell) ? 'text-right tabular-nums' : ''}`}
                  style={{ color: cell === null ? 'var(--text-3)' : 'var(--text)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}
                >
                  {cell === null ? 'null' : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** One panel: its error, or its warning, or its chart. */
export function PanelChart({ panel }: { panel: PanelRun }) {
  if (panel.error) {
    return (
      <div
        role="alert"
        data-testid="dashboard-panel-error"
        className="rounded-md px-3 py-2 text-xs"
        style={{ background: 'var(--error-cont)', color: 'var(--on-error-cont)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}
      >
        {panel.error.message}
      </div>
    )
  }
  if (panel.warning) {
    return (
      <div
        data-testid="dashboard-panel-warning"
        className="rounded-md px-3 py-2 text-xs"
        style={{ background: 'color-mix(in srgb, var(--amber) 14%, transparent)', color: 'var(--amber)' }}
      >
        {panel.warning}
      </div>
    )
  }
  switch (panel.kind) {
    case 'number':
      return <NumberChart panel={panel} />
    case 'bar':
      return <BarChart panel={panel} stacked={false} />
    case 'stacked_bar':
      return <BarChart panel={panel} stacked />
    case 'line':
      return <LineChart panel={panel} />
    case 'table':
      return <TableChart panel={panel} />
    default:
      return (
        <div data-testid="dashboard-panel-warning" className="text-xs" style={{ color: 'var(--amber)' }}>
          This panel names a chart kind the app does not draw: {panel.kind}.
        </div>
      )
  }
}
