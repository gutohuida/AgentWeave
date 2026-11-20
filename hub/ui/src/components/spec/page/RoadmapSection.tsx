import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import { useDeclineNextSliceOffer, useNextSliceOffers, useTakeNextSliceOffer } from '@/api/nextSlice'
import { useMoveSlice, useRemoveSlice, useStartSliceConversation } from '@/api/roadmapEdits'
import { useArchiveBatch, type ArchiveBatchResult } from '@/api/specTidy'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { openConversationAt } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { RoadmapSlices, type RoadmapSliceView } from './RoadmapSlices'
import type { SpecDocumentView } from './model'
import '@/styles/roadmap.css'

/** The choice that means "the roadmap's author": the Hub resolves it. */
const AUTHOR = ''

/** An agent to choose, the roadmap's author first. */
function AgentPicker({
  label,
  agents,
  author,
  busy,
  action,
  onPick,
  onCancel,
}: {
  label: string
  agents: string[]
  author: string | null
  busy: boolean
  action: string
  onPick: (agent: string) => void
  onCancel: () => void
}) {
  const [agent, setAgent] = React.useState(author ?? AUTHOR)
  return (
    <span className="aw-rm-picker" data-testid="rm-agent-picker">
      <select aria-label={label} value={agent} disabled={busy} onChange={(e) => setAgent(e.target.value)}>
        {author === null ? <option value={AUTHOR}>The roadmap&apos;s author</option> : null}
        {agents.map((name) => (
          <option key={name} value={name}>
            {name}
            {name === author ? ' (the author)' : ''}
          </option>
        ))}
      </select>
      <Button variant="primary" size="xs" disabled={busy} onClick={() => onPick(agent)}>
        {action}
      </Button>
      <Button variant="ghost" size="xs" disabled={busy} onClick={onCancel}>
        Cancel
      </Button>
    </span>
  )
}

function viewOf(doc: SpecDocumentView): RoadmapSliceView[] {
  return (doc.slices ?? []).map((s) => {
    const p = s.progress
    return {
      key: s.key,
      title: s.title,
      intent: s.intent,
      done: s.done,
      buildsAfter: s.buildsAfter,
      state: p?.state ?? (s.document ? 'drafting' : 'not_drafted'),
      document: s.document ? { path: s.document.path, title: s.document.title } : undefined,
      tasks: p?.tasks && p.tasks.total > 0 ? p.tasks : undefined,
      costUsd: p?.costUsd ?? undefined,
      unpriced: p?.unpriced,
      at: p?.at ?? undefined,
      waitsFor: p?.waitsFor,
      offersDrafting: p?.offersDrafting,
      retrospective: p?.state === 'built' ? p.retrospective : undefined,
      warning: p?.warning,
      addedAfterApproval: p?.addedAfterApproval,
      addedBy: p?.addedBy,
    }
  })
}

/** Open a conversation: the app reads where it is from the address. */
const openConversation = openConversationAt

/** A roadmap's slices on its page, wired to the Hub (`a-roadmap-that-is-recognisably-a-roadmap`):
 *  drafting offers, the operator's reorder and remove, "Add a slice with an agent" (a conversation,
 *  never a form), and the done state with its archive confirmation. */
export function RoadmapSection({ doc, now, onOpenDocument }: { doc: SpecDocumentView; now: Date; onOpenDocument?: (path: string) => void }) {
  const projectId = useConfigStore((s) => s.selectedProjectId) ?? ''
  const queryClient = useQueryClient()
  const { data: agentRows = [], error: agentsError } = useAgents()
  const { data: offers = [], error: offersError } = useNextSliceOffers()
  const take = useTakeNextSliceOffer()
  const decline = useDeclineNextSliceOffer()
  const move = useMoveSlice()
  const remove = useRemoveSlice()
  const converse = useStartSliceConversation()
  const archive = useArchiveBatch()
  const [editing, setEditing] = React.useState(false)
  const [picking, setPicking] = React.useState<string | null>(null)
  const [confirming, setConfirming] = React.useState(false)
  const [notice, setNotice] = React.useState<string | null>(null)
  const [plan, setPlan] = React.useState<ArchiveBatchResult['plan'] | null>(null)

  const slices = viewOf(doc)
  const agents = agentRows.map((a) => a.name)
  const approved = doc.phase === 'approved'
  const failure = [take.error, decline.error, move.error, remove.error, converse.error, archive.error, agentsError, offersError].find(Boolean)
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['project', projectId] })
  const authorOf = (key: string) => offers.find((o) => o.roadmap === doc.path && o.next_slice.key === key)?.agent ?? null

  const finished = slices.length > 0 && slices.every((s) => s.state === 'built')
  const toArchive = finished
    ? [
        ...(doc.phase === 'archived' ? [] : [{ path: doc.path, title: doc.title }]),
        ...(doc.slices ?? []).filter((s) => s.document && !s.document.archived).map((s) => ({ path: s.document!.path, title: s.document!.title })),
      ]
    : []

  const pickerFor = (target: string) => {
    if (picking !== target) return null
    const author = target === 'add' ? null : authorOf(target)
    return (
      <AgentPicker
        label={target === 'add' ? 'Agent to add the slice with' : 'Agent that drafts this slice'}
        agents={agents}
        author={author}
        busy={take.isPending || converse.isPending}
        action={target === 'add' ? 'Start the conversation' : 'Draft'}
        onCancel={() => setPicking(null)}
        onPick={(agent) => {
          if (target === 'add') {
            converse.mutate(
              { roadmap: doc.path, agent: agent || undefined },
              {
                onSuccess: (started) => {
                  setPicking(null)
                  const result = started as { agent: string; conversation_id: string }
                  openConversation(projectId, result.agent, result.conversation_id, doc.path)
                },
              },
            )
          } else {
            take.mutate(
              { roadmap: doc.path, slice: target, agent: agent || author || agents[0] || '' },
              {
                onSuccess: (taken) => {
                  setPicking(null)
                  void refresh()
                  // The slice's document exists now (FR-1): open it, and the drafting turn is
                  // bound to it.
                  if (taken?.document) onOpenDocument?.(taken.document.path)
                },
              },
            )
          }
        }}
      />
    )
  }

  return (
    <div className="aw-rm-section" data-testid="roadmap-section">
      {finished ? (
        <div className="aw-rm-done" data-testid="rm-done">
          <Icon name="check_circle" size={16} />
          <span>
            <strong>This roadmap is done.</strong> Every slice is built.
          </span>
          {toArchive.length ? (
            <Button
              variant="outline"
              size="xs"
              onClick={() => {
                setConfirming(true)
                setPlan(null)
                // Asks the Hub what archiving would do to each document; archives nothing.
                archive.mutate(
                  { paths: toArchive.map((d) => d.path), check_only: true, no_capability_change: true },
                  { onSuccess: (result) => setPlan((result as ArchiveBatchResult).plan ?? []) },
                )
              }}
            >
              <Icon name="archive" size={12} />
              Archive the roadmap and its slices
            </Button>
          ) : null}
        </div>
      ) : null}
      {notice ? (
        <p className="aw-rm-warn" role="status">
          {notice}
        </p>
      ) : null}
      {failure ? (
        <p className="aw-rm-warn" role="alert" data-testid="rm-failure">
          {readableApiError(failure, 'The Hub refused this.')}
        </p>
      ) : null}
      <RoadmapSlices
        slices={slices}
        draftRule="ready"
        editing={editing && approved}
        now={now}
        figures={doc.progress}
        onEditingChange={setEditing}
        onDraft={(key) => setPicking(key)}
        onNotNow={(key) => decline.mutate({ roadmap: doc.path, slice: key })}
        onOpenDocument={(path) => onOpenDocument?.(path)}
        onOpenRetrospective={(path) => onOpenDocument?.(path)}
        onMove={(key, to) => move.mutate({ roadmap: doc.path, slice: key, position: to + 1 })}
        onRemove={(key) =>
          remove.mutate(
            { roadmap: doc.path, slice: key },
            {
              onSuccess: (result) => {
                const dropped = (result as { dropped_from_builds_after?: string[] } | undefined)?.dropped_from_builds_after
                setNotice(dropped?.length ? `Removed. ${dropped.join(', ')} no longer build after it.` : null)
              },
            },
          )
        }
        onAddWithAgent={() => setPicking('add')}
        pickerFor={pickerFor}
      />
      {confirming ? (
        <div className="aw-rm-confirm" role="dialog" aria-modal="true" aria-labelledby="rm-archive-title" data-testid="rm-archive-confirm">
          <h3 id="rm-archive-title">
            Archive {toArchive.length} {toArchive.length === 1 ? 'document' : 'documents'}?
          </h3>
          <p className="aw-rm-muted">This cannot be undone. Nothing is archived until you confirm.</p>
          <ul>
            {toArchive.map((d) => {
              const will = plan?.find((p) => p.path === d.path)
              return (
                <li key={d.path} data-will={will?.will}>
                  {d.title}
                  {will ? (
                    <span className="aw-rm-muted">
                      {' — '}
                      {will.will === 'archive'
                        ? 'will be archived'
                        : will.will === 'archive_no_capability_change'
                          ? 'built and not folded into a capability: will be archived stating it changes none'
                          : `cannot be archived: ${will.reason ?? will.code ?? 'refused'}`}
                    </span>
                  ) : null}
                </li>
              )
            })}
          </ul>
          {plan?.some((p) => p.will === 'refuse') ? (
            <p className="aw-rm-warn" role="alert">
              Nothing will be archived while any of these is refused.
            </p>
          ) : null}
          <div className="aw-rm-confirm-actions">
            <Button variant="ghost" size="xs" disabled={archive.isPending} onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="xs"
              disabled={archive.isPending || !plan || plan.some((p) => p.will === 'refuse')}
              onClick={() =>
                archive.mutate(
                  { paths: toArchive.map((d) => d.path), all_or_none: true, no_capability_change: true },
                  {
                    onSuccess: (result) => {
                      setConfirming(false)
                      const refused = (result as { refused?: Array<{ path: string; reason: string }> }).refused ?? []
                      setNotice(refused.length ? `Not archived: ${refused.map((r) => `${r.path} (${r.reason})`).join('; ')}` : null)
                    },
                  },
                )
              }
            >
              Archive
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
