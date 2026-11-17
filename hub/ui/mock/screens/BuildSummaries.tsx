import * as React from 'react'
import { needsLine, summaryOf } from '@/components/builds/buildViewModel'
import { RunningTab } from '@/components/panel/RunningTab'
import { runningItems } from '@/components/panel/runningModel'
import { SpecBuildsSection } from '@/components/spec/page/SpecBuilds'
import { toast } from '@/lib/toast'
import type { ScreenProps } from '../routes'
import { buildFor, buildHref, colorIndexer, nowFor, projectRowOf, RECORDED_BUILDS, specCardOf, useBuildHash } from '../buildsMock'
import '@/styles/spec-page.css'

const colorIndexOf = colorIndexer(RECORDED_BUILDS)

/** The two compact summaries in their real containers, side by side for review: the spec page's
 *  Builds section at its document column's width, and the side panel's Running tab at its
 *  narrowest, 360px. Both are fed the same two recorded builds (the running one, in its `live`
 *  mock state, and a finished one with send-backs), so their counts can be read against each other
 *  and against the build view they open. */
export default function BuildSummaries({ go }: ScreenProps) {
  const { state } = useBuildHash()
  const live = state === 'recorded' ? 'live' : state
  const reads = React.useMemo(
    () => [buildFor('build-e36c054f9e59', live), buildFor('build-04e780a89c1c', 'recorded')].filter((r): r is NonNullable<typeof r> => r !== null),
    [live],
  )
  const open = (id: string, task?: string) => {
    window.location.hash = buildHref(id, task, id === 'build-e36c054f9e59' ? live : undefined).slice(1)
  }
  const cards = reads
    .map((read, i) => ({
      ...specCardOf(read, i + 1),
      summary: { model: summaryOf(read, nowFor(read)), hrefFor: (task?: string) => buildHref(read.build.id, task), onOpen: (task?: string) => open(read.build.id, task) },
    }))
    .reverse()
  const rows = reads.map((read) => projectRowOf(read))
  const now = nowFor(reads[0] ?? null)
  const items = runningItems({ builds: rows, loops: [], jobs: [], now, buildNeeds: Object.fromEntries(reads.map((r) => [r.build.id, needsLine(r)])) })
  const summaries = Object.fromEntries(reads.map((read) => [read.build.id, summaryOf(read, nowFor(read))]))

  return (
    <div className="mock-build-summaries">
      <div className="aw-sp-main mock-build-summaries-spec">
        <p className="mock-build-summaries-label">The spec page: its Builds section, at the document column’s width</p>
        <div className="aw-sp-columns">
          <div className="aw-sp-content">
            <SpecBuildsSection
              builds={cards}
              canBuild={false}
              now={now}
              flash={null}
              onStartBuild={() => undefined}
              onOpenRuns={(b) => toast({ title: `Opens Build ${b.number}'s ${b.runs} runs in Traces` })}
              onStop={() => toast({ title: 'Stops the build' })}
              onCopyLink={() => undefined}
            />
          </div>
          <div className="aw-sp-rail" />
        </div>
      </div>
      <aside className="mock-build-summaries-panel" aria-label="Side panel at 360px">
        <p className="mock-build-summaries-label">The side panel’s Running tab, at 360px</p>
        <div className="mock-build-summaries-frame">
          <RunningTab
            items={items}
            colorIndexOf={colorIndexOf}
            onOpen={(item) => toast({ title: 'Opens the spec at its builds', description: item.title })}
            onAttend={() => go({ kind: 'build', buildId: 'build-e36c054f9e59' })}
            buildSummaries={summaries}
            buildHref={(id, task) => buildHref(id, task)}
            onOpenBuild={open}
          />
        </div>
      </aside>
    </div>
  )
}
