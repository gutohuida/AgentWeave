import { useEffect, useRef } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import { DEFAULT_QUESTION_TIMEOUT_SECONDS, useQuestions, type Question } from '@/api/questions'
import { AnswerForm } from './AnswerForm'
import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/common/Badge'
import { hubDate } from '@/lib/hubTime'

/** Share of the asker's window that must have gone before the timestamp turns amber.
 *
 * Three quarters leaves a quarter — 60s on the 240s default, about as long as reading a question
 * and typing an answer takes. Deliberately a colour step and a phrase, never a ticking number:
 * `design/mocks/S6/RESEARCH.md` found countdown pressure makes approval decisions worse, and the
 * permission card states its expiry consequence in words for the same reason. Undoing that here
 * would contradict a decision already made on the neighbouring surface.
 */
const URGENCY_FRACTION = 0.75

/** True once nobody is on the other end: the run that asked has ended, so its `ask_user` call is
 *  gone and an answer now reaches the agent as a new message rather than as the answer it was
 *  waiting for. Absent means "assume yes", matching the Hub's own presumption. */
function stillWaiting(question: Question): boolean {
  return question.asker_waiting !== false
}

function QuestionRow({
  question,
  blocking = false,
  timeoutSeconds,
}: {
  question: Question
  blocking?: boolean
  /** This agent's `question_timeout_seconds`, or the built-in default when it sets none. */
  timeoutSeconds: number
}) {
  const labelId = `question-${question.id}`
  // Same fact and same wording as `AgentQuestionCard`, which reached this conclusion first. A
  // second vocabulary for "nobody is holding for this" would just be two ways of saying dead.
  const nobodyWaiting = !stillWaiting(question)
  // Only a blocking question with someone still on the other end can run out of time. The window
  // is per-agent (`Agent.question_timeout_seconds`, carried to the spawned run as
  // `AW_QUESTION_TIMEOUT`); a whole `ask_user` batch shares one deadline, started when the
  // questions were created, so the row's own `created_at` is the right base for every member.
  const elapsedSeconds = (Date.now() - hubDate(question.created_at).getTime()) / 1000
  const urgent = blocking && !nobodyWaiting && elapsedSeconds >= timeoutSeconds * URGENCY_FRACTION

  return (
    <article className={`question-row p-4${nobodyWaiting ? ' is-stale' : ''}`}>
      <div className="mb-1 flex items-center justify-between gap-3">
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-[13px] font-medium" style={{ color: blocking ? 'var(--red)' : 'var(--text)' }}>{question.from_agent}</span>
          {nobodyWaiting && (
            <span
              className="shrink-0"
              data-testid={`question-stale-${question.id}`}
              title="The run that asked this has ended. Answering now would reach it as a new message, not as the answer it was waiting for."
              style={{ fontSize: 10, color: 'var(--text-3)' }}
            >
              no longer waiting
            </span>
          )}
        </span>
        <time
          className={`question-time shrink-0 text-[11px] tabular-nums${urgent ? ' is-urgent' : ''}`}
          data-testid={`question-time-${question.id}`}
          dateTime={question.created_at}
          title={urgent
            ? `${question.from_agent} waits ${timeoutSeconds}s for an answer to this and most of that has gone. If it runs out the run stops waiting and carries on without one.`
            : undefined}
        >
          {formatDistanceToNow(hubDate(question.created_at), { addSuffix: true })}
          {urgent ? ' · asker times out soon' : ''}
        </time>
      </div>
      <p id={labelId} className="text-sm leading-6" style={{ color: 'var(--text)' }}>{question.question}</p>
      <AnswerForm question={question} labelledBy={labelId} />
    </article>
  )
}

export function QuestionsPanel() {
  const pageRef = useRef<HTMLDivElement>(null)
  const { data: unanswered, isLoading, isError, error } = useQuestions(false)
  const { data: answered } = useQuestions(true)
  // The questions payload carries no timeout of its own — the window belongs to the agent that
  // asked, and the roster is the only place this surface can reach it. Joining here costs nothing:
  // every other screen already holds this query under the same key.
  const { data: agents } = useAgents()

  // The overview's Answer button can sit below the fold. Browser automation and keyboard users
  // both scroll it into view before activating it; this panel then replaces the overview inside
  // the same scroll container. Reset that inherited position so the destination starts with its
  // heading and the highest-stakes blocking question instead of halfway through an answer form.
  useEffect(() => {
    pageRef.current?.closest('.workspace-content')?.scrollTo({ top: 0 })
  }, [])

  if (isLoading) {
    return (
      <div ref={pageRef} className="questions-page space-y-3 p-5" aria-label="Loading questions">
        {[0, 1].map((item) => (
          <div key={item} className="question-row p-4" aria-hidden="true">
            <div className="trust-state-skeleton w-24" />
            <div className="trust-state-skeleton mt-3 w-full" />
            <div className="trust-state-skeleton mt-2 w-3/4" />
            <div className="trust-state-skeleton mt-4 h-14 w-full" />
          </div>
        ))}
      </div>
    )
  }

  // A failed fetch used to fall through to "No pending questions" — an error rendered as
  // reassurance, on the one screen where "nothing is waiting on you" is the most expensive thing
  // to say wrongly. Say what actually happened instead, and say that this list is not evidence.
  //
  // Only when there is nothing to show. The 3s poll means one dropped request sets `isError`
  // while React Query still holds the last good list; replacing a screen of real questions with
  // an error card would cost the operator more than the blip did. That case gets the banner
  // below instead.
  if (isError && unanswered === undefined) {
    return (
      <div ref={pageRef} className="questions-page flex justify-center p-5">
        <div className="trust-state" role="alert" data-testid="questions-error">
          <span className="trust-state-icon is-error"><Icon name="error_outline" size={22} /></span>
          <h1 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Can&apos;t load questions</h1>
          <p className="mx-auto mt-2 text-xs" style={{ maxWidth: 320, color: 'var(--text-3)' }}>
            {readableApiError(error, 'The Hub did not return the pending questions.')}
          </p>
          <p className="mx-auto mt-2 text-xs" style={{ maxWidth: 320, color: 'var(--text-3)' }}>
            An agent may be blocked on an answer this list cannot show. An empty screen here does
            not mean nothing is waiting on you.
          </p>
        </div>
      </div>
    )
  }

  const questionTimeout = (agentName: string) =>
    agents?.find((agent) => agent.name === agentName)?.question_timeout_seconds
    ?? DEFAULT_QUESTION_TIMEOUT_SECONDS

  // A blocking question whose asker has ended is not blocking anything, so it does not belong
  // under a banner asserting that agents are waiting. Partitioning on both facts is what makes
  // that banner true of every row inside it — the panel can verify `asker_waiting` per row, and
  // asserting it collectively while ignoring it individually is the dishonest half.
  const blocking = unanswered?.filter((question) => question.blocking && stillWaiting(question)) ?? []
  const rest = unanswered?.filter((question) => !question.blocking || !stillWaiting(question)) ?? []

  return (
    <div ref={pageRef} className="questions-page space-y-5 p-5">
      <header>
        <h1 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>Questions</h1>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>Decisions waiting for an operator answer.</p>
      </header>

      {/* The list rendered below is the last one that arrived, not the current one. Said out loud
          because the panel polls: without it a question asked during the outage is simply absent,
          and absence here reads as "nothing is waiting on you". */}
      {isError && (
        <p className="questions-stale-banner" role="status" data-testid="questions-stale">
          <Icon name="warning" size={14} />
          {readableApiError(error, 'The Hub stopped answering.')} This list is the last one that
          loaded, so a newer question may be missing from it.
        </p>
      )}

      {blocking.length > 0 && (
        <section className="rounded-[var(--radius-xl)] p-4" aria-labelledby="blocking-questions" style={{ background: 'color-mix(in srgb, var(--red) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)' }}>
          <h2 id="blocking-questions" className="mb-3 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--red)' }}>
            <Icon name="warning" size={17} /> Blocking — agents are waiting for your answer
          </h2>
          <div className="space-y-3">
            {blocking.map((question) => (
              <QuestionRow key={question.id} question={question} timeoutSeconds={questionTimeout(question.from_agent)} blocking />
            ))}
          </div>
        </section>
      )}

      {rest.length > 0 && (
        <section aria-labelledby="unanswered-questions">
          <h2 id="unanswered-questions" className="mb-3 text-sm font-medium" style={{ color: 'var(--text)' }}>Unanswered</h2>
          <div className="space-y-2.5">
            {rest.map((question) => (
              <QuestionRow key={question.id} question={question} timeoutSeconds={questionTimeout(question.from_agent)} />
            ))}
          </div>
        </section>
      )}

      {unanswered?.length === 0 && <EmptyState icon="help" title="No pending questions" description="Agent questions will appear here." />}

      {answered && answered.length > 0 && (
        <details className="answered-questions mt-2">
          <summary className="flex cursor-pointer select-none items-center text-[13px] font-medium transition-colors" style={{ color: 'var(--text-3)' }}>
            <Icon name="expand_more" size={16} className="mr-1" /> Answered ({answered.length})
          </summary>
          <div className="mt-3 space-y-2">
            {answered.map((question) => (
              <article key={question.id} className="question-row p-3 opacity-65">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{question.from_agent}</span>
                  <Badge variant="success">answered</Badge>
                </div>
                <p className="text-xs" style={{ color: 'var(--text)' }}>{question.question}</p>
                {question.answer && <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>→ {question.answer}</p>}
              </article>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
