import type { OverviewBody, OverviewFinished, OverviewItemTarget } from '@/api/overview'
import { formatCount } from '@/lib/format'
import { hubDate } from '@/lib/hubTime'
import {
  buildDestination,
  environmentDestination,
  goTo,
  projectDestination,
  resolveEnvironmentSection,
} from '@/lib/navigation'
import { useTaskFilterStore } from '@/store/taskFilterStore'
import type { OverviewTabId } from '@/store/overviewTabsStore'
import type { OverviewTarget } from './OverviewDashboard'
import type { FinishedTally, MainHealth, SpendFigures } from './overviewDashboardModel'

/** The live Overview's rules outside React: where each item opens, and the Dashboard's figures
 *  from the one Hub read. Shared by both tabs, so a figure on one never contradicts the other. */

export const overviewTabDomId = (tab: OverviewTabId) => `overview-tab-${tab}`
export const overviewPanelDomId = (tab: OverviewTabId) => `overview-panel-${tab}`

export interface OverviewScreenProps {
  onNavigate: (page: string) => void
  /** Opens the Add-agent dialog for this project (F808). */
  onAddAgent?: () => void
  /** Opens one conversation; without it a row opens its agent's latest conversation. */
  onOpenConversation?: (agent: string, conversationId: string) => void
}

/** The ways out of the Overview, given the project: every item's click lands on its detail (FR-12). */
export interface OverviewOpeners {
  openTask: (taskId: string) => void
  openConversation: (agent: string, conversationId: string) => void
  /** An item's own target: the thread, task, build, request, check or setting it is about. */
  openTarget: (target: OverviewItemTarget, agent: string | null) => void
  /** A tile or a foot link. */
  openPlace: (target: OverviewTarget) => void
}

export function useOverviewOpeners(projectId: string, props: OverviewScreenProps): OverviewOpeners {
  const { onNavigate, onOpenConversation } = props
  const openTask = (taskId: string) => {
    useTaskFilterStore.getState().setPendingOpenTaskId(taskId)
    onNavigate('tasks')
  }
  const openConversation = (agent: string, conversationId: string) =>
    onOpenConversation ? onOpenConversation(agent, conversationId) : onNavigate(`agent:${agent}`)
  const openThreadOf = (agent: string | null, conversationId: string | null | undefined) => {
    if (agent && conversationId) openConversation(agent, conversationId)
    else if (agent) onNavigate(`agent:${agent}`)
    else onNavigate('thread')
  }
  const openTarget = (target: OverviewItemTarget, agent: string | null) => {
    switch (target.type) {
      case 'thread':
        return openThreadOf(agent, target.conversation_id ?? target.id)
      case 'task':
        return target.id ? openTask(target.id) : onNavigate('tasks')
      case 'build':
        return goTo(buildDestination(projectId, target.id))
      case 'permission':
        // A request is decided in the thread whose turn asked; without one, where decisions list.
        return target.conversation_id && agent ? openConversation(agent, target.conversation_id) : onNavigate('questions')
      case 'check':
        return goTo(environmentDestination(projectId, 'checks'))
      case 'setting':
        return goTo(environmentDestination(projectId, resolveEnvironmentSection(target.id) ?? undefined))
      case 'spec':
        return goTo(projectDestination(projectId, 'spec', target.path ?? target.id))
    }
  }
  const openPlace = (target: OverviewTarget) => {
    switch (target) {
      case 'needs':
        return onNavigate('tasks')
      case 'running':
      case 'finished':
        return onNavigate('activity')
      case 'spend':
        return onNavigate('ledger')
      case 'main':
        return goTo(environmentDestination(projectId, 'checks'))
      case 'builds':
        return goTo(projectDestination(projectId, 'spec'))
      case 'chapters':
        return onNavigate('thread')
      case 'profiles':
        return goTo(projectDestination(projectId, 'profiles'))
      case 'dashboards':
        return goTo(projectDestination(projectId, 'dashboards'))
    }
  }
  return { openTask, openConversation, openTarget, openPlace }
}

/** Since the operator's local midnight: what the Hub sends covers min(day_start, last visit). */
function isToday(at: string, now: Date): boolean {
  const d = hubDate(at)
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
}

/** A finished item's cost when it is not in dollars: credits, tokens, or "not priced" (FR-7). */
export function finishedCostWords(item: OverviewFinished): string | null {
  if (item.usd != null) return null
  if (item.credits != null) return `${formatCount(item.credits)} ${item.credits === 1 ? 'credit' : 'credits'}`
  return 'not priced'
}

/** The Dashboard's props from the one read: the mapping is plain, so each tab reads the same
 *  figures (FR-10). */
export function dashboardFigures(body: OverviewBody, now: Date) {
  const main: MainHealth = {
    state: body.main.state,
    branch: body.main.branch,
    heldLandings: body.main.held_landings,
    knownFailing: body.main.fails_on_main,
    flaky: body.main.flaky,
    detail: body.main.detail,
  }
  const days = body.spend.days
  const today = days[days.length - 1]
  const spend: SpendFigures = {
    todayUsd: today?.usd ?? null,
    periodUsd: days.some((d) => d.usd != null) ? days.reduce((s, d) => s + (d.usd ?? 0), 0) : null,
    periodLabel: `over ${days.length} days`,
    budgetUsd: null,
    trend: days.map((d) => ({ day: d.day, usd: d.usd })),
    unpricedTurns: days.reduce((s, d) => s + d.unpriced_turns, 0),
    days: days.map((d) => ({ day: d.day, usd: d.usd, tokens: d.tokens, credits: d.credits, unpricedTurns: d.unpriced_turns })),
    tokenBudget: body.spend.token_budget,
  }
  const todays = body.finished.filter((f) => isToday(f.at, now))
  const finishedToday: FinishedTally = {
    landed: todays.filter((f) => f.outcome === 'landed').length,
    sentBack: todays.filter((f) => f.outcome === 'sent_back').length,
    failed: todays.filter((f) => f.outcome === 'failed').length,
  }
  return { main, spend, finishedToday, todays }
}

