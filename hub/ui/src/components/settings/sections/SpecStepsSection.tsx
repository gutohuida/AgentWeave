import { readableApiError } from '@/api/client'
import { useProjectJourney, useSaveProjectJourney, type JourneyStep } from '@/api/spec'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { toast } from '@/lib/toast'
import { SpecStepsSettings } from '../SpecStepsSettings'

const HEADING = { icon: 'list_tree', title: 'Spec steps', description: 'The steps a spec change walks, in order. Add your own, or add an instruction to any step.' }

/** A step is custom when it carries its own text; a built-in step is its key alone. */
const isCustom = (step: JourneyStep) => step.instructions !== undefined

/** What goes on the wire: built-in steps by key (plus an added instruction), custom steps with
 *  their text and sizes. Only what a step holds, so saving an unchanged list sends what it read. */
function toEntry(step: JourneyStep): JourneyStep {
  const append = step.append?.trim() ? { append: step.append } : {}
  if (!isCustom(step)) return { key: step.key, ...append }
  return { key: step.key, title: step.title, instructions: step.instructions, sizes: step.sizes, ...append }
}

/** Project settings → Spec steps, on the Hub. Each change saves the whole list at once; the Hub
 *  validates it, and a refusal is shown with the Hub's reason while the list stays as last stored
 *  (the list is read from the Hub's answer, never from an edit it has not accepted). */
export function SpecStepsSection() {
  const { data, error, refetch } = useProjectJourney()
  const save = useSaveProjectJourney()

  if (error && !data) {
    return (
      <SettingsPage {...HEADING}>
        <SettingsNotice tone="error" title="This project's spec steps could not be read." testId="spec-steps-load-error" action={{ label: 'Retry', onClick: () => void refetch() }}>
          <p>{readableApiError(error, 'The Hub did not return a reason.')}</p>
        </SettingsNotice>
      </SettingsPage>
    )
  }
  if (!data) {
    return (
      <SettingsPage {...HEADING}>
        <SettingsLoading label="Loading spec steps" rows={4} />
      </SettingsPage>
    )
  }

  return (
    <SpecStepsSettings
      steps={data.steps}
      diagnostics={data.diagnostics}
      notices={
        save.isError ? (
          <SettingsNotice tone="error" title="That change was not saved." testId="spec-steps-refusal">
            <p>{readableApiError(save.error, 'The Hub did not return a reason.')}</p>
          </SettingsNotice>
        ) : null
      }
      onChange={(steps, said) => {
        save.reset()
        save.mutate(
          { steps: steps.map(toEntry) },
          {
            onSuccess: () => toast({ title: said, tone: 'success' }),
            onError: (err) => toast({ title: 'Not saved', description: readableApiError(err, 'The steps could not be saved.'), tone: 'error' }),
          },
        )
      }}
    />
  )
}
