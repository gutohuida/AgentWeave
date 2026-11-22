import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { ChatModelPicker } from '@/components/agents/pool/ChatModelPicker'
import { chatChoice, chatPickOverrides, entryLabel, modelLabel } from '@/components/agents/pool/poolModel'
import { BuildPlanDialog } from '@/components/spec/BuildPlanDialog'
import { toast } from '@/lib/toast'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { BuildChoices } from '@/api/spec'
import type { ScreenProps } from '../routes'
import { POOL_AGENTS, POOL_CATALOG, POOL_RECOMMENDED, POOL_RUNNERS, POOL_TASKS, POOLS } from '../poolMock'

/** The profile-pool slice's two surfaces outside settings, for review: the Build dialog choosing a
 *  model per task (`#profile-pools/build`) and the composer's pool picker (`#profile-pools/chat`).
 *  The pool editor itself is on the agent's own Running page (`#agent-settings/Builder/running`). */
export default function ProfilePools({ route }: ScreenProps) {
  const view = route.kind === 'profile-pools' ? route.view : 'build'
  return view === 'chat' ? <ChatPickers /> : <BuildChoice />
}

function BuildChoice() {
  const [open, setOpen] = React.useState(true)
  const pools = React.useMemo(() => ({ byAgent: POOLS, runners: POOL_RUNNERS, catalog: POOL_CATALOG }), [])
  return (
    <div className="mock-pool-page">
      <p className="mock-pool-lede">
        The pool slice’s own seven tasks, built by Developer and checked by QA and QA2, each profile with its own models.
      </p>
      <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
        <Icon name="play_arrow" size={14} /> Build
      </Button>
      <BuildPlanDialog
        open={open}
        onOpenChange={setOpen}
        title="A profile’s pool of runners and models"
        approve={false}
        recommended={POOL_RECOMMENDED}
        tasks={POOL_TASKS}
        agents={POOL_AGENTS}
        pools={pools}
        now={new Date('2026-11-19T10:00:00Z')}
        onConfirm={(choices: BuildChoices) => {
          setOpen(false)
          const lines = POOL_TASKS.map((t) => {
            const pick = choices.task_builder_entries?.[t.key]
            const entry = POOLS[choices.task_builders?.[t.key] || 'Developer']?.find((e) => e.runner_id === pick?.runner_id && e.effort === pick?.effort)
            return entry ? entryLabel(POOL_CATALOG, entry) : 'default'
          })
          toast({ title: 'Build started', description: `Builders run on ${lines.join(', ')}.`, tone: 'success' })
        }}
      />
    </div>
  )
}

/** mock state: three conversations of Developer, one of Architect. */
function ChatPickers() {
  const developer = POOLS.Developer!
  const architect = POOLS.Architect!
  return (
    <div className="mock-pool-page">
      <p className="mock-pool-lede">The composer’s model pill under a pool. Open each to compare.</p>
      <Composer agentName="Developer" pool={developer} startedOn={null} title="A new chat: every model in the pool can be chosen" />
      <Composer
        agentName="Developer"
        pool={developer}
        startedOn="claude"
        initial={developer.find((e) => e.effort === 'high' && e.cli === 'claude')}
        title="A chat already running on Claude Code: Codex is listed, not choosable"
      />
      <Composer agentName="Architect" pool={architect} startedOn="claude" title="A profile with one model: shown, nothing to open" />
    </div>
  )
}

function Composer({ agentName, pool, startedOn, initial, title }: { agentName: string; pool: AgentPoolEntry[]; startedOn: string | null; initial?: AgentPoolEntry; title: string }) {
  const [overrides, setOverrides] = React.useState<Record<string, string>>(initial ? { runner_id: initial.runner_id, ...(initial.effort ? { effort: initial.effort } : {}) } : {})
  const current = chatChoice(POOL_CATALOG, pool, overrides)
  return (
    <section className="mock-pool-composer" aria-label={title}>
      <h3 className="mock-pool-composer-title">{title}</h3>
      <div className="mock-pool-composer-box">
        <p className="mock-pool-composer-placeholder">Message {agentName}…</p>
        <div className="mock-pool-composer-bar">
          <ChatModelPicker
            agentName={agentName}
            pool={pool}
            catalog={POOL_CATALOG}
            current={current}
            startedOn={startedOn}
            onPick={(pick) => {
              setOverrides(chatPickOverrides(POOL_CATALOG, overrides, pick))
              const label = pick.kind === 'entry' ? entryLabel(POOL_CATALOG, pick.entry) : modelLabel(POOL_CATALOG, pick.provider, pick.model)
              toast({ title: `This chat runs on ${label}`, tone: 'success' })
            }}
          />
        </div>
      </div>
    </section>
  )
}
