import * as React from 'react'
import { useAgents } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { useCharters, useCreateCharter, useDeleteCharter, useUpdateCharter, type Charter } from '@/api/charters'
import { CharterForm } from '@/components/charters/CharterForm'
import { DeleteCharterDialog } from '@/components/charters/DeleteCharterDialog'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { toast } from '@/lib/toast'
import { ChartersSettings } from '../ChartersSettings'

/** Project settings → Charters, on the Hub: the list, reading one, the charter dialog, and the
 *  delete confirmation (a charter delete is a hard delete, F186). */
export function ChartersSection() {
  const { data: charters, isLoading, error, refetch } = useCharters()
  const { data: agents = [], error: agentsError } = useAgents()
  const createCharter = useCreateCharter()
  const updateCharter = useUpdateCharter()
  const deleteCharter = useDeleteCharter()
  const [creating, setCreating] = React.useState(false)
  const [editing, setEditing] = React.useState<Charter | null>(null)
  const [confirmingDelete, setConfirmingDelete] = React.useState<Charter | null>(null)
  // The create/update refusal, rendered inside the form that caused it (F187). Cleared whenever a
  // form opens or submits, so a sentence about the previous attempt never describes this one.
  const [formError, setFormError] = React.useState<string | null>(null)
  const [deleteError, setDeleteError] = React.useState<string | null>(null)

  // A failed read is said, with a Retry: never a skeleton that waits for an answer that is not
  // coming, and never rows that could be saved over settings that were never read.
  if (error && !charters) {
    return (
      <SettingsPage icon="menu_book" title="Charters" description="What an agent is accountable for and where its authority ends.">
        <SettingsNotice tone="error" title="The charters could not be read." action={{ label: 'Retry', onClick: () => void refetch() }}>
          <p>{readableApiError(error, 'The Hub did not return a reason.')}</p>
        </SettingsNotice>
      </SettingsPage>
    )
  }
  if (isLoading || !charters) {
    return (
      <SettingsPage icon="menu_book" title="Charters" description="What an agent is accountable for and where its authority ends.">
        <SettingsLoading label="Loading charters" rows={3} />
      </SettingsPage>
    )
  }

  return (
    <>
      <ChartersSettings
        charters={charters}
        boundTo={(charter) => agents.filter((agent) => agent.charter_id === charter.id).map((agent) => agent.name)}
        deleting={deleteCharter.isPending}
        notices={
          <>
            {/* Which agents hold each charter is read from the roster; unread, every charter would
                look unbound. */}
            {agentsError ? (
              <SettingsNotice tone="warning" title="Which agents hold each charter could not be read." testId="charters-bound-error">
                <p>A charter shown with no agents may still be bound.</p>
              </SettingsNotice>
            ) : null}
            {deleteError ? (
              <SettingsNotice tone="error" title="The charter was not deleted.">
                <p>{deleteError}</p>
              </SettingsNotice>
            ) : null}
          </>
        }
        onNew={() => {
          setFormError(null)
          setCreating(true)
        }}
        onEdit={(charter) => {
          setFormError(null)
          setEditing(charter)
        }}
        onDelete={(charter) => setConfirmingDelete(charter)}
      />
      {creating ? (
        <CharterForm
          title="New charter"
          initial={null}
          isPending={createCharter.isPending}
          error={formError}
          onCancel={() => setCreating(false)}
          onSubmit={(values) => {
            setFormError(null)
            createCharter.mutate(values, {
              onSuccess: () => {
                setCreating(false)
                toast({ title: `${values.name} added`, tone: 'success' })
              },
              onError: (error: unknown) => setFormError(readableApiError(error, 'The Hub refused this charter.')),
            })
          }}
        />
      ) : null}
      {editing ? (
        <CharterForm
          title={`Edit ${editing.name}`}
          initial={editing}
          isPending={updateCharter.isPending}
          error={formError}
          onCancel={() => setEditing(null)}
          onSubmit={(updates) => {
            setFormError(null)
            updateCharter.mutate(
              { id: editing.id, updates },
              {
                onSuccess: () => {
                  setEditing(null)
                  toast({ title: `${updates.name} saved`, tone: 'success' })
                },
                onError: (error: unknown) => setFormError(readableApiError(error, 'The Hub refused this change.')),
              },
            )
          }}
        />
      ) : null}
      {confirmingDelete ? (
        <DeleteCharterDialog
          name={confirmingDelete.name}
          content={confirmingDelete.content}
          onCancel={() => setConfirmingDelete(null)}
          onConfirm={() => {
            const charter = confirmingDelete
            setConfirmingDelete(null)
            setDeleteError(null)
            deleteCharter.mutate(charter.id, {
              onSuccess: () => toast({ title: `${charter.name} deleted`, tone: 'success' }),
              onError: (error: unknown) => setDeleteError(readableApiError(error, 'Could not delete charter')),
            })
          }}
        />
      ) : null}
    </>
  )
}
