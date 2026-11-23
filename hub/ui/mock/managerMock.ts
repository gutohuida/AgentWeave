import type { QueryClient } from '@tanstack/react-query'
import { managerRunsKey, type ManagerEndedRun, type ManagerRunningRun, type ManagerUnseenFailure } from '@/api/manager'

/** The manager's runs for the top bar's indicator and the items' icons
 *  (`background-manager-work-you-can-see`), in the order their routes answer: running and unseen
 *  oldest first; recent ends newest first. Times are relative to this window's clock, so elapsed
 *  times read as they would live. */
export function seedManagerRuns(client: QueryClient, projectId: string): void {
  const ago = (s: number) => new Date(Date.now() - s * 1000).toISOString()
  const running: ManagerRunningRun[] = [
    { run_id: 'mrun-titles0001', job: 'conversation-titles', subject: { conversation_id: 'conv-1' }, trigger: 'turn_completed', initiator: 'autonomous', started_at: ago(14), conversation_id: null },
    { run_id: 'mrun-distil0001', job: 'vault-distillation', subject: { source: 'src-acme-kickoff' }, trigger: 'source_added', initiator: 'autonomous', started_at: ago(48), conversation_id: null },
    { run_id: 'run-mender0001', job: 'mender', subject: { stall: 'stall-1', reason: 'BWYCS-4 waited 40 min for a review' }, trigger: 'stall', initiator: 'autonomous', started_at: ago(95), conversation_id: 'conv-mender-1' },
  ]
  const unseen: ManagerUnseenFailure[] = [
    { run_id: 'mrun-check0001', job: 'spec-vault-check', subject: { document: 'spec/changes/background-manager-work-you-can-see/spec.json' }, ended_at: ago(3600), detail: 'The runner refused the model claude-no-such-model.' },
  ]
  const ended: ManagerEndedRun[] = [
    { run_id: 'mrun-retro0001', job: 'build-retrospective', subject: { document: 'spec/changes/leaner-navigation/spec.json' }, trigger: 'last_task_approved', initiator: 'autonomous', started_at: ago(700), ended_at: ago(520), outcome: 'written', detail: null, conversation_id: null },
  ]
  client.setQueryData(managerRunsKey(projectId, 'running'), running)
  client.setQueryData(managerRunsKey(projectId, 'unseen'), unseen)
  client.setQueryData(managerRunsKey(projectId, 'ended-live'), ended)
  client.setQueryData(['project', projectId, 'manager', 'activity', 'runs'], [])
}
