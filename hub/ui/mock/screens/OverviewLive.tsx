import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { localDayStart, type OverviewBody } from '@/api/overview'
import { OverviewScreen } from '@/components/overview/OverviewScreen'
import { toast } from '@/lib/toast'
import { PROJECT_ID } from '../fixtures'
import { NEXT_FIXTURES, type OverviewNextState } from '../overviewNextMock'
import type { ScreenProps } from '../routes'

// mock state: the approved mock's three shapes, restated as `GET /overview` bodies, so the screen
// on view is the app's own OverviewScreen reading its own query key. Times are before the real
// clock, because the live screen counts "today" from it.
function liveBody(state: OverviewNextState): OverviewBody {
  const f = NEXT_FIXTURES[state]
  const at = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString()
  const kind = (k: string) => (k === 'blocked' ? 'question' : k) as OverviewBody['needs'][number]['kind']
  const midnight = new Date()
  midnight.setHours(0, 0, 0, 0)
  return {
    generated_at: at(0),
    visit: null,
    needs: f.needs.map((n, i) => ({
      id: n.id,
      kind: kind(n.kind),
      rank: i + 1,
      agent: n.agent,
      title: n.title,
      waiting_since: at(n.ago),
      action: n.action,
      target: { type: 'task', id: `task-${n.id}` },
    })),
    running: f.running.map((r) => ({ run_id: r.id, agent: r.agent, conversation_id: `conv-${r.id}`, task_id: null, what: r.what, started_at: at(r.ago) })),
    finished: f.finished.map((a) => ({
      id: a.id,
      task_id: `task-${a.id}`,
      run_id: null,
      agent: a.agent,
      title: a.what,
      outcome: a.outcome === 'running' ? 'landed' : a.outcome,
      at: at(a.ago),
      usd: a.usd ?? null,
      tokens: 1200,
      credits: null,
    })),
    spend: {
      days: f.spend.trend.map((t, i) => {
        const day = new Date(midnight.getTime() - (f.spend.trend.length - 1 - i) * 86_400_000)
        return { day: day.toISOString(), usd: t.usd, tokens: 40_000, credits: null, unpriced_turns: t.usd == null ? 2 : 0 }
      }),
      token_budget: f.spend.budgetUsd != null && f.spend.periodUsd != null ? { limit: 1_000_000, used: Math.round((f.spend.periodUsd / f.spend.budgetUsd) * 1_000_000) } : null,
    },
    main: {
      state: f.main.state,
      branch: f.main.branch,
      held_landings: f.main.heldLandings ?? 0,
      fails_on_main: f.main.knownFailing,
      flaky: f.main.knownFailing == null ? null : 1,
      detail: f.main.detail ?? null,
    },
    builds: f.builds.map((b) => ({ build_id: b.id, document_path: null, title: b.title, tasks_done: b.done, tasks_total: b.total, stage_words: b.stage, needs_operator: b.needsYou })),
    note: null,
    note_writing: false,
    note_last_attempt: null,
  }
}

/** The live Overview, tabs and all, fed the approved mock's shapes (`?state=quiet|trouble`). */
export default function OverviewLive({ route }: ScreenProps) {
  const state = route.kind === 'overview-live' ? route.state : 'busy'
  const client = useQueryClient()
  // Seeded before the screen first reads it, so it never asks a Hub that is not there.
  React.useState(() => client.setQueryData(['project', PROJECT_ID, 'overview', localDayStart()], liveBody(state)))
  React.useEffect(() => {
    client.setQueryData(['project', PROJECT_ID, 'overview', localDayStart()], liveBody(state))
  }, [client, state])
  const say = (where: string) => toast({ title: `Would open ${where}` })
  return <OverviewScreen onNavigate={(page) => say(page)} onOpenConversation={(agent) => say(`${agent}'s thread`)} />
}
