import * as React from 'react'
import { readableApiError } from '@/api/client'
import { useInstructions, useInstructionsSource, useSaveInstructions } from '@/api/instructions'
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
  const source = useInstructionsSource()
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

  const inAgentsMd = data.source === 'agents_md'
  const write = (content: string) =>
    save.mutate(content, {
      onSuccess: (saved) =>
        saved?.notice
          ? toast({ title: 'AGENTS.md saved, not committed', description: saved.notice, tone: 'neutral' })
          : toast({
              title: 'Instructions saved',
              description: inAgentsMd
                ? `AGENTS.md was committed on ${data.main_branch ?? 'the main branch'}. New sessions read it; running ones keep what they started with.`
                : 'New sessions read them; running ones keep what they started with.',
              tone: 'success',
            }),
    })
  const switchSource = (agentsMd: boolean) =>
    source.mutate(agentsMd, {
      onSuccess: (switched) =>
        toast({
          title: agentsMd ? 'AGENTS.md is now the instructions' : "The Hub's instructions are back in use",
          description: switched?.notice ?? undefined,
          tone: switched?.notice ? 'neutral' : 'success',
        }),
    })

  const sourceNotice = inAgentsMd ? (
    <SettingsNotice
      testId="instructions-source-agents-md"
      title="These instructions are this project's AGENTS.md."
      action={{ label: "Use the Hub's instructions instead", onClick: () => switchSource(false) }}
    >
      <p>
        Saving writes the file and commits it, alone, on {data.main_branch ? <code>{data.main_branch}</code> : 'the main branch'}. A save is refused while AGENTS.md has uncommitted changes or the checkout is on another branch.
      </p>
    </SettingsNotice>
  ) : data.agents_md_offered ? (
    <SettingsNotice
      testId="instructions-source-offer"
      title="This project's folder has an AGENTS.md."
      action={{ label: "Use AGENTS.md as this project's instructions", onClick: () => switchSource(true) }}
    >
      <p>
        Agents are given the instructions below, not that file. Using AGENTS.md instead adds these instructions to it in one commit on the main branch; they stay kept here, unused, should you switch back.
      </p>
    </SettingsNotice>
  ) : null

  return (
    <>
      <InstructionsSettings
        content={data.content}
        maxChars={data.max_chars}
        saving={save.isPending}
        justSaved={justSaved}
        notices={
          <>
            {sourceNotice}
            {source.isError ? (
              <SettingsNotice tone="error" title="Where the instructions come from was not changed.">
                <p>{readableApiError(source.error, 'The Hub did not return a reason.')}</p>
              </SettingsNotice>
            ) : null}
            {save.isError ? (
              <SettingsNotice tone="error" title="These instructions were not saved.">
                <p>{readableApiError(save.error, 'The Hub did not return a reason.')} What you typed is still here; press Save to try again.</p>
              </SettingsNotice>
            ) : null}
          </>
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
