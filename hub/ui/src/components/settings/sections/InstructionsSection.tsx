import * as React from 'react'
import { readableApiError } from '@/api/client'
import { useInstructions, useSaveInstructions } from '@/api/instructions'
import { useProjects } from '@/api/projects'
import { ClearInstructionsDialog } from '@/components/instructions/ClearInstructionsDialog'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { InstructionsSettings } from '../OtherSettings'

const DESCRIPTION = "Rules every agent in this project reads at the start of a session, before its own charter."

/**
 * Project settings → Instructions, editable only once they have actually been read.
 *
 * `data` is tested first (F271): a failed read renders no editor at all, so Save can never write
 * an empty box over instructions that were never read; and a background refetch that fails keeps
 * the loaded editor on screen, since React Query keeps the last good `data`.
 *
 * Saving an empty editor over stored instructions destroys them, and nothing keeps a copy, so that
 * one save asks first. The test trims both sides; what is written is never trimmed.
 */
export function InstructionsSection() {
  const { data, isError, error, refetch } = useInstructions()
  const save = useSaveInstructions()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projects = [] } = useProjects()
  const [confirmingClear, setConfirmingClear] = React.useState<string | null>(null)
  const [justSaved, setJustSaved] = React.useState(false)
  React.useEffect(() => {
    if (!save.isSuccess) return
    setJustSaved(true)
    const timer = setTimeout(() => setJustSaved(false), 2000)
    return () => clearTimeout(timer)
  }, [save.isSuccess, save.submittedAt])

  if (!data) {
    return (
      <SettingsPage icon="description" title="Instructions" description={DESCRIPTION}>
        {isError ? (
          <SettingsNotice tone="error" title="This project's instructions could not be loaded." action={{ label: 'Retry', onClick: () => void refetch() }}>
            <p>{readableApiError(error, 'The Hub did not return a reason.')}</p>
            <p>Nothing stored has been changed. The editor stays hidden rather than showing an empty one, so it cannot overwrite instructions it never read.</p>
          </SettingsNotice>
        ) : (
          <SettingsLoading label="Loading instructions" rows={2} />
        )}
      </SettingsPage>
    )
  }

  const write = (content: string) =>
    save.mutate(content, {
      onSuccess: () => toast({ title: 'Instructions saved', description: 'New sessions read them; running ones keep what they started with.', tone: 'success' }),
    })

  return (
    <>
      <InstructionsSettings
        content={data.content}
        maxChars={data.max_chars}
        saving={save.isPending}
        justSaved={justSaved}
        notices={
          save.isError ? (
            <SettingsNotice tone="error" title="These instructions were not saved.">
              <p>{readableApiError(save.error, 'The Hub did not return a reason.')} What you typed is still here; press Save to try again.</p>
            </SettingsNotice>
          ) : null
        }
        onSave={(content) => {
          if (data.content.trim() !== '' && content.trim() === '') {
            setConfirmingClear(content)
            return
          }
          write(content)
        }}
      />
      {confirmingClear !== null ? (
        <ClearInstructionsDialog
          projectName={projects.find((project) => project.id === projectId)?.name ?? 'this project'}
          storedContent={data.content}
          // Cancel leaves the editor exactly as typed.
          onCancel={() => setConfirmingClear(null)}
          onConfirm={() => {
            const content = confirmingClear
            setConfirmingClear(null)
            write(content)
          }}
        />
      ) : null}
    </>
  )
}
