import { readableApiError } from '@/api/client'
import { useSpecRequirements } from '@/api/spec'
import { SpecRetiredRequirements } from './SpecRetiredRequirements'
import type { HeaderNotice } from './page/SpecNotices'

/** The retired requirements as one notice of the redesigned header (spec
 *  `the-spec-header-redesigned`): its line counts them, and its body is this list, open. A failed
 *  read is a notice too, never a list that silently is not there (F197). */
export function useRetiredRequirementsNotice(path: string, onOpenTasks?: (taskIds: string[]) => void): HeaderNotice | null {
  const { data, isError, error } = useSpecRequirements(path)
  if (isError) {
    return {
      id: 'retired-error',
      tone: 'warn',
      testId: 'spec-retired-error',
      summary: `Could not load retired requirements: ${readableApiError(error, 'the Hub did not answer.')}`,
    }
  }
  const count = (data?.requirements ?? []).filter((row) => row.state === 'retired').length
  if (count === 0) return null
  return {
    id: 'retired',
    tone: 'info',
    summary: `${count} retired requirement${count === 1 ? '' : 's'}, and the work still pointing at them`,
    body: <SpecRetiredRequirements path={path} onOpenTasks={onOpenTasks} defaultOpen />,
  }
}
