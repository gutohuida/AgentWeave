import * as React from 'react'
import { readableApiError } from '@/api/client'
import {
  useAgents,
  useFoldAgent,
  useFoldPreview,
  type FoldOpenWork,
  type FoldPreview,
  type FoldSettingDifference,
} from '@/api/agents'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogTrigger } from '@/components/ui/dialog'
import { MenuSelect } from '@/components/ui/menu'
import { toast } from '@/lib/toast'
import { describeSettingValue } from '@/lib/foldPresentation'

/** What the preview calls each setting, in the words the settings pages use. */
const SETTING_LABELS: Record<string, string> = {
  runner: 'Runner and model',
  charter: 'Charter',
  can_read_checkpoints: 'May read other agents’ checkpoints',
  can_recall: 'May recall other agents’ observations',
  can_accept_evidence: 'May accept evidence',
  can_admin_specs: 'May tidy the specifications',
  default_permission_mode: 'Permission posture',
  reach_grants: 'Reach beyond the workspace',
  checkpoint_policy: 'Checkpoint policy',
  permission_timeout_seconds: 'Permission timeout',
  question_timeout_seconds: 'Question timeout',
}

const KIND_LABELS: Record<string, string> = {
  task: 'Task',
  build: 'Build',
  job: 'Job',
  loop: 'Loop',
  flow: 'Flow',
}

const FIELD_LABELS: Record<string, string> = {
  assignee: 'assigned to it',
  builder: 'it builds',
  checker: 'it checks',
  agent: 'it runs',
  pending_agent: 'its staged edit',
  builders: 'listed builder',
  reviewers: 'listed reviewer',
  lead: 'it leads',
}

function Section({ title, testId, children }: { title: string; testId: string; children: React.ReactNode }) {
  return (
    <section className="mt-3" aria-label={title} data-testid={testId}>
      <h3 className="text-xs font-semibold" style={{ color: 'var(--text)' }}>
        {title}
      </h3>
      <div className="mt-1 text-xs" style={{ color: 'var(--text-2)' }}>
        {children}
      </div>
    </section>
  )
}

function DifferenceRow({ difference, source, profile }: { difference: FoldSettingDifference; source: string; profile: string }) {
  const label = SETTING_LABELS[difference.setting] ?? difference.setting
  return (
    <li data-testid={`fold-difference-${difference.setting}`}>
      <span style={{ color: 'var(--text)' }}>{label}</span>: {source} has {describeSettingValue(difference.setting, difference.source)};{' '}
      {profile} keeps {describeSettingValue(difference.setting, difference.profile)}.
    </li>
  )
}

function WorkRow({ item, profile }: { item: FoldOpenWork; profile: string }) {
  return (
    <li data-testid="fold-open-work">
      {KIND_LABELS[item.kind] ?? item.kind} “{item.title}” ({FIELD_LABELS[item.field] ?? item.field}) moves to {profile}.
    </li>
  )
}

/** What the preview says, in the order that matters to the decision: what stops it, what the
 *  operator gives up, what is added, and what work moves. */
export function FoldPreviewBody({ preview }: { preview: FoldPreview }) {
  const { source, profile } = preview
  return (
    <div data-testid="fold-preview">
      {preview.refusals.length > 0 ? (
        <div role="alert" className="text-xs" data-testid="fold-refusals" style={{ color: 'var(--amber)' }}>
          <p className="font-semibold">{source} cannot be folded yet:</p>
          <ul className="ml-4 list-disc">
            {preview.refusals.map((refusal) => (
              <li key={`${refusal.code}-${refusal.message}`}>{refusal.message}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <Section title={`Settings ${profile} keeps`} testId="fold-differences">
        {preview.setting_differences.length === 0 ? (
          <p>{source} and {profile} have the same settings. Nothing is dropped.</p>
        ) : (
          <>
            <p>{profile}’s settings win. Where {source} differs, its setting is dropped:</p>
            <ul className="ml-4 mt-1 list-disc space-y-0.5">
              {preview.setting_differences.map((difference) => (
                <DifferenceRow key={difference.setting} difference={difference} source={source} profile={profile} />
              ))}
            </ul>
          </>
        )}
      </Section>

      <Section title={`Added to ${profile}’s runners`} testId="fold-pool">
        {preview.pool_entries_added.length === 0 ? (
          <p>Nothing: {profile} already has every runner {source} could use.</p>
        ) : (
          <ul className="ml-4 list-disc space-y-0.5">
            {preview.pool_entries_added.map((entry) => (
              <li key={entry.id} data-testid="fold-pool-entry">
                {entry.runner_name}
                {entry.model ? ` · ${entry.model}` : ''}
                {entry.effort ? ` · ${entry.effort} effort` : ''}
              </li>
            ))}
          </ul>
        )}
        {(preview.profile_changes ?? []).map((change) => (
          <p key={change.setting} className="mt-1" data-testid="fold-profile-change">
            {profile} has no runner of its own, so it takes the first one added as its default.
          </p>
        ))}
      </Section>

      <Section title="Open work that moves" testId="fold-work">
        {preview.open_work.length === 0 ? (
          <p>None. {source} has no open tasks, builds or jobs.</p>
        ) : (
          <ul className="ml-4 list-disc space-y-0.5">
            {preview.open_work.map((item) => (
              <WorkRow key={`${item.kind}-${item.id}-${item.field}`} item={item} profile={profile} />
            ))}
          </ul>
        )}
        <p className="mt-1">Finished work, runs and conversations keep the name {source}.</p>
      </Section>
    </div>
  )
}

function FoldBody({ agent, onDone }: { agent: string; onDone: () => void }) {
  const { data: roster = [] } = useAgents()
  const profiles = roster.filter((candidate) => candidate.name !== agent && candidate.lifecycle !== 'archived' && !candidate.folded_into)
  const [into, setInto] = React.useState<string | null>(null)
  const { data: preview, error, isLoading } = useFoldPreview(agent, into)
  const fold = useFoldAgent()
  const confirm = () => {
    if (!into) return
    fold.mutate(
      { agent, into },
      {
        onSuccess: () => {
          toast({ title: `${agent} folded into ${into}`, tone: 'success' })
          onDone()
        },
      },
    )
  }
  const canConfirm = !!into && !!preview?.can_fold && !fold.isPending

  return (
    <>
      <div className="flex items-center gap-2 text-xs">
        <label htmlFor="fold-profile" style={{ color: 'var(--text-2)' }}>
          Profile
        </label>
        <MenuSelect
          id="fold-profile"
          testId="fold-profile-select"
          label="Fold into"
          value={into ?? ''}
          onChange={setInto}
          placeholder="Choose the agent to keep…"
          options={profiles.map((profile) => ({ value: profile.name, label: profile.name }))}
        />
      </div>
      {isLoading ? <p className="mt-3 text-xs" style={{ color: 'var(--text-3)' }}>Checking what would change…</p> : null}
      {error ? (
        <p role="alert" className="mt-3 text-xs" style={{ color: 'var(--amber)' }}>
          {readableApiError(error, 'Could not read what folding would do.')}
        </p>
      ) : null}
      {preview ? <FoldPreviewBody preview={preview} /> : null}
      {fold.error ? (
        <p role="alert" className="mt-3 text-xs" data-testid="fold-error" style={{ color: 'var(--amber)' }}>
          {readableApiError(fold.error, `Could not fold ${agent}.`)}
        </p>
      ) : null}
      <footer className="mt-4 flex justify-end gap-2">
        <DialogClose asChild>
          <Button variant="ghost" size="sm">
            Keep {agent}
          </Button>
        </DialogClose>
        <Button variant="destructive" size="sm" data-testid="fold-confirm" disabled={!canConfirm} onClick={confirm}>
          {fold.isPending ? 'Folding…' : into ? `Fold ${agent} into ${into} — cannot be undone` : `Fold ${agent}`}
        </Button>
      </footer>
    </>
  )
}

/** The Fold into… action beside Archive: folds this agent into another as one profile, its history
 *  kept. The dialog shows the preview route's answer before anything is confirmed. */
export function FoldAgentDialog({ agent }: { agent: string }) {
  const [open, setOpen] = React.useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="agent-fold-open">
          Fold into…
        </Button>
      </DialogTrigger>
      <DialogContent
        title={`Fold ${agent} into another agent?`}
        description={`${agent} is archived for good and its work and settings join the agent you choose. Its conversations, runs and checkpoints stay readable under ${agent}; it accepts no new turn.`}
        width={620}
      >
        <FoldBody agent={agent} onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  )
}
