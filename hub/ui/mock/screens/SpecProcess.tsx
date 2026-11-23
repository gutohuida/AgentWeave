import * as React from 'react'
import type { PreMortem as PreMortemFiring, PreMortemFinding } from '@/api/manager'
import { BuildPlanDialog } from '@/components/spec/BuildPlanDialog'
import { SpecPreMortemSection } from '@/components/spec/page/SpecPreMortem'
import { SpecPossibleFacts, type SpecPossibleFact } from '@/components/spec/page/SpecPossibleFacts'
import { SpecSidePanel, SpecWorkspace } from '@/components/spec/page/SpecWorkspace'
import { useListPreferences } from '@/components/spec/page/hooks'
import { toast } from '@/lib/toast'
import { PROJECT_ID } from '../fixtures'
import type { ScreenProps } from '../routes'
import { useSpecMock } from '../specMock'
import '@/styles/spec-page.css'

// The findings are the pre-mortem this project's Hub wrote for spdoc-ca259b88896c at 21:04 on
// 2026-11-23 (event evt-b6d0d4e90a15), cut to their first sentences. The answers are what the
// Architect actually did with each. mock state: no Hub records answers yet, so `answer` is added here.
const NOW = new Date('2026-11-23T22:50:00Z')
const BY = 'Architect'

const FINDINGS: PreMortemFinding[] = [
  {
    requirement: 'FR-2',
    story: "The 'important facts' lists ship mostly empty: no requirement lists a fact and only one fact has ever been opened, so 'Cited by a spec' shows 0 and 'Opened by agents' 1.",
    cites: ["design: 'no requirement lists a fact in `facts`'", 'hub/hub/vault_spec_check.py:118-138'],
    answer: { note: 'Each list now says why it is empty (FR-2, criterion important-empty-lists). Getting specs to cite facts is the separate spec-process change the operator agreed.', by: BY, at: '2026-11-23T21:39:00Z' },
  },
  {
    requirement: 'FR-3',
    story: 'The project-wide uses route scans 175 firings over 110 documents per request with no time bound, so the Overview can stall.',
    cites: ['hub/hub/api/v1/vault.py:638-659', 'criteria uses-route-rule'],
    answer: { note: 'FR-3 now answers within one second on this project’s data; criterion uses-route-rule times it on a read-only copy.', by: BY, at: '2026-11-23T21:39:00Z' },
  },
  {
    requirement: 'FR-9',
    story: 'Keystrokes overlap and an answer for an earlier word arrives last, so the page shows hits for text no longer in the box.',
    cites: ['criteria text-route-answers'],
    answer: { note: 'FR-10 now says the Documents results are always the current text’s; criterion search-current-text resolves two answers out of order.', by: BY, at: '2026-11-23T21:39:00Z' },
  },
  {
    requirement: 'FR-1',
    story: 'Counts drift between the Overview, the rail and the views on a mixed real vault, because the test has one orphan fact and no archived source.',
    cites: ['criteria overview-counts-agree', 'hub/ui/src/components/vault/VaultLibrary.tsx:98-112'],
    answer: null,
  },
  {
    requirement: 'FR-6',
    story: 'A fact with no line citation, a changed source or a missing source opens nowhere sensible; only a clean line-3 citation is tested.',
    cites: ['criteria facts-view-order', 'criteria drive-vault-explains-itself'],
    answer: null,
  },
  {
    requirement: 'FR-12',
    story: 'If the container never passes `uses`, the live page silently keeps today’s library and the component tests still pass.',
    cites: ["design: 'VaultLibrary showing them only when its container passes `uses`'"],
    answer: { note: 'Not changed: the acceptance drive fails on today’s build at its first check (no Overview), so an unwired page cannot pass it, whatever the data.', by: BY, at: '2026-11-23T21:39:00Z' },
  },
]

const firing = (findings: PreMortemFinding[]): PreMortemFiring => ({
  id: 'firing-premortem-vault',
  at: '2026-11-23T21:04:16Z',
  trigger: 'criteria_written',
  model: 'claude-sonnet-5-5',
  outcome: 'written',
  detail: null,
  cost_usd_micros: 101_933,
  findings,
})

const LATER: Record<number, string> = {
  3: 'The counts criterion now includes an archived source (overview-counts-agree).',
  4: 'FR-6 now specifies all three; criterion facts-open-unusual tests them.',
}
const ALL_ANSWERED = FINDINGS.map((f, i) => (f.answer ? f : { ...f, answer: { note: LATER[i], by: BY, at: '2026-11-23T21:41:00Z' } }))

type StateKey = 'partly' | 'none-answered' | 'answered' | 'never' | 'running'
const STATES: Array<{ key: StateKey; caption: string; preMortems: PreMortemFiring[]; running?: boolean }> = [
  { key: 'partly', caption: '4 of 6 answered: two still open, the check lists a gap', preMortems: [firing(FINDINGS)] },
  { key: 'none-answered', caption: 'Just written: nothing answered yet', preMortems: [firing(FINDINGS.map((f) => ({ ...f, answer: null })))] },
  { key: 'answered', caption: 'Every finding answered: no gap', preMortems: [firing(ALL_ANSWERED)] },
  { key: 'never', caption: 'No pre-mortem has run', preMortems: [] },
  { key: 'running', caption: 'Running', preMortems: [], running: true },
]

function stateFromHash(): (typeof STATES)[number] {
  const q = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  return STATES.find((s) => s.key === q.get('pm')) ?? STATES[0]
}

function PreMortemAt({ state, onCopyLink }: { state: (typeof STATES)[number]; onCopyLink: (anchor: string) => void }) {
  return (
    <SpecPreMortemSection
      preMortems={state.preMortems}
      jobOff={false}
      running={state.running ?? false}
      refusal={null}
      pending={false}
      now={NOW}
      flash={null}
      onCopyLink={onCopyLink}
      onRun={() => toast({ title: 'Pre-mortem asked for', tone: 'success' })}
      onOpenManager={() => toast({ title: 'Opens Settings › Manager' })}
    />
  )
}

function Caption({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 mt-0 text-[11px] font-medium uppercase tracking-wide" style={{ color: 'var(--text-3)' }}>
      {children}
    </p>
  )
}

/** The side panel at a conversation's width with the pre-mortem at the end of its Document tab,
 *  beside the section in each state at the same width. */
function PanelView() {
  const { surface, planDialog } = useSpecMock('spec-process/panel')
  const current = stateFromHash()
  return (
    <div style={{ display: 'flex', gap: 24, height: '100%', minHeight: 0, padding: 16, boxSizing: 'border-box' }}>
      <div style={{ width: 480, flex: 'none', minHeight: 0, border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', display: 'flex' }} data-testid="spec-panel">
        <div className="h-full min-w-0 flex-1">
          <SpecSidePanel
            {...surface}
            // mock state: the pre-mortem moves from the Builds tab to the end of the Document tab.
            retrospective={undefined}
            preMortem={({ onCopyLink }) => <PreMortemAt state={current} onCopyLink={onCopyLink} />}
            initialAnchor={new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('at') ?? undefined}
          />
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 0, maxWidth: 480, overflow: 'auto', display: 'grid', gap: 28, alignContent: 'start' }}>
        {STATES.map((s) => (
          <div key={s.key}>
            <Caption>{s.caption}</Caption>
            <PreMortemAt state={s} onCopyLink={() => toast({ title: 'Link copied', tone: 'success' })} />
          </div>
        ))}
      </div>
      <BuildPlanDialog {...planDialog} />
    </div>
  )
}

/** The full spec page: the pre-mortem after the document's requirements, and possible backing facts
 *  under two requirements. */
function PageView() {
  const { surface, layout, entries, planDialog } = useSpecMock('spec-process/page')
  const [listPrefs, setListPrefs] = useListPreferences(PROJECT_ID)
  const current = stateFromHash()
  const ids = surface.doc.requirements.map((r) => r.identifier)
  // mock state: what a spec-vault check that names possible backing facts might answer.
  const possible: SpecPossibleFact[] = [
    { requirement: ids[0] ?? '', fact: 'fct-3b1f0c2a9e41', claim: 'Every requirement in a change document carries at least one acceptance criterion before approval.', source: 'spec-flow-rules.md' },
    { requirement: ids[0] ?? '', fact: 'fct-a07c55d1e2b9', claim: 'Approval is the operator’s decision; agents never approve a document.', source: 'Meeting 2026-10-08 spec journey' },
    { requirement: ids[1] ?? '', fact: 'fct-9d2e7b40c613', claim: 'Gaps warn and never gate: the operator can always approve anyway.', source: null },
  ]
  return (
    <>
      <SpecWorkspace
        key={layout}
        {...surface}
        retrospective={undefined}
        preMortem={({ onCopyLink }) => <PreMortemAt state={current} onCopyLink={onCopyLink} />}
        requirementAside={(id) => <SpecPossibleFacts facts={possible.filter((f) => f.requirement === id)} />}
        entries={entries}
        listPrefs={listPrefs}
        onListPrefsChange={setListPrefs}
        onNew={() => toast({ title: 'Starts a new change' })}
        layout={layout}
      />
      <BuildPlanDialog {...planDialog} />
    </>
  )
}

export default function SpecProcess({ route }: ScreenProps) {
  return route.kind === 'spec-process' && route.view === 'page' ? <PageView /> : <PanelView />
}