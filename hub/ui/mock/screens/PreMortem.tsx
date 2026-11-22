import * as React from 'react'
import type { PreMortem as PreMortemFiring } from '@/api/manager'
import { SpecPreMortemSection } from '@/components/spec/page/SpecPreMortem'
import { toast } from '@/lib/toast'
import type { ScreenProps } from '../routes'
import '@/styles/spec-page.css'

// mock state: no Hub fires this job yet, so the firings below are written for the mock. Their
// findings are the kind the job is meant to find, about this very change.
const NOW = new Date('2026-11-22T23:40:00Z')

const WRITTEN: PreMortemFiring = {
  id: 'firing-premortem-2',
  at: '2026-11-22T23:31:00Z',
  trigger: 'criteria_written',
  model: 'claude-sonnet-5-5',
  outcome: 'written',
  detail: null,
  cost_usd_micros: 184_000,
  findings: [
    {
      story: 'The agent advanced past intake on its own while the operator was still thinking about the playback, so the question they cared about was never asked. Nothing on screen said a step had moved.',
      requirement: 'FR-7',
      cites: ['spec_journey.py:529 ASK_TO_ADVANCE', 'criterion drive-advances-unasked'],
    },
    {
      story: 'A fresh conversation opened on a document whose problem was already written skipped the playback, and the operator never got to check the agent understood them in that thread.',
      requirement: 'FR-13',
      cites: ['criterion playback-duty-text'],
    },
    {
      story: 'The cap of three questions pushed the challenge to the premise into a later turn, after the requirements were written on top of it.',
      requirement: 'FR-5',
      cites: ['FR-3 premise-and-failure'],
    },
  ],
}

const FAILED: PreMortemFiring = {
  id: 'firing-premortem-1',
  at: '2026-11-22T22:58:00Z',
  trigger: 'requested',
  model: 'claude-sonnet-5-5',
  outcome: 'failed',
  detail: 'The runner exited before answering (exit code 1).',
  cost_usd_micros: null,
  findings: [],
}

const STATES: Array<{ caption: string; preMortems: PreMortemFiring[]; jobOff?: boolean; running?: boolean; refusal?: string }> = [
  { caption: 'The job is off in this project', preMortems: [], jobOff: true },
  { caption: 'On, never run', preMortems: [] },
  { caption: 'Running, after Run a pre-mortem', preMortems: [], running: true },
  { caption: 'Refused: the job has no runner', preMortems: [], refusal: 'The Pre-mortem job has no runner. Choose one in Manager.' },
  { caption: 'Written, with an earlier failed firing', preMortems: [WRITTEN, FAILED] },
  { caption: 'The latest firing failed', preMortems: [FAILED, WRITTEN] },
]

function Caption({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 mt-0 text-[11px] font-medium uppercase tracking-wide" style={{ color: 'var(--text-3)' }}>
      {children}
    </p>
  )
}

/** The spec page's Pre-mortem section in each state it can be in, at the document column's width.
 *  Its job's on/off, runner, model and firing choice are on Settings › Manager, which lists the
 *  job from the Hub's registry like every other. */
export default function PreMortem({ go }: ScreenProps) {
  return (
    <div style={{ maxWidth: 820, margin: '0 auto', padding: '24px 16px 64px', display: 'grid', gap: 28 }}>
      {STATES.map((s) => (
        <div key={s.caption}>
          <Caption>{s.caption}</Caption>
          <SpecPreMortemSection
            preMortems={s.preMortems}
            jobOff={s.jobOff ?? false}
            running={s.running ?? false}
            refusal={s.refusal ?? null}
            pending={false}
            now={NOW}
            flash={null}
            onCopyLink={() => toast({ title: 'Link copied', tone: 'success' })}
            onRun={() => toast({ title: 'Pre-mortem asked for', tone: 'success' })}
            onOpenManager={() => go({ kind: 'settings', section: 'manager' })}
          />
        </div>
      ))}
    </div>
  )
}
