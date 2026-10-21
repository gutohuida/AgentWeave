import * as React from 'react'
import type { Question } from '@/api/questions'
import { AgentQuestionCard } from '@/components/agents/AgentQuestionCard'
import { Composer, type ComposerProps } from '@/components/agents/Composer'
import '@/styles/conversation.css'

/** The composer with the question it is answering docked inside it.
 *
 *  A pending `ask_user` question used to float above the composer as a separate card (and, with
 *  little conversation, take the transcript's room). Here it is the top section of the composer's
 *  own surface, separated by a hairline, and the box below is where the answer is written: one
 *  object, one place to answer from (T3's pattern). The composer itself is today's `Composer`. */
export function ConversationComposerDock({
  questions,
  conversationId,
  selected,
  onToggleOption,
  onDecline,
  isResponding = false,
  isDeclining = false,
  composer,
  children,
  areaRef,
}: {
  /** This agent's pending questions; empty or absent docks nothing. */
  questions?: Question[]
  /** The conversation on screen: only a question asked in it docks here (F804). */
  conversationId?: string | null
  selected: string[]
  onToggleOption: (label: string) => void
  onDecline?: (questionId: string) => void
  isResponding?: boolean
  isDeclining?: boolean
  composer: ComposerProps & { key?: React.Key }
  /** Banners and notices that belong above the surface (BannerStack, Continue). */
  children?: React.ReactNode
  /** The area's root, for callers that measure the panel's room (the interjection tray). */
  areaRef?: React.Ref<HTMLDivElement>
}) {
  const [draft, setDraft] = React.useState('')
  const hasQuestion = (questions?.length ?? 0) > 0
  const { key, ...composerProps } = composer
  return (
    <div ref={areaRef} className="conversation-composer-fade shrink-0" data-testid="conversation-composer-area">
      <div className="mx-auto flex w-full max-w-[820px] flex-col gap-2">
        {children}
        <div className="conversation-composer-surface" data-has-question={hasQuestion ? 'true' : 'false'}>
          {hasQuestion ? (
            <AgentQuestionCard
              docked
              questions={questions!}
              conversationId={conversationId}
              agent={composerProps.agent}
              selected={selected}
              onToggle={onToggleOption}
              isResponding={isResponding}
              isTyping={draft.trim().length > 0}
              onDecline={onDecline}
              isDeclining={isDeclining}
            />
          ) : null}
          <Composer
            key={key}
            {...composerProps}
            canSubmitEmpty={hasQuestion && selected.length > 0}
            placeholder={hasQuestion ? `Answer ${composerProps.agent}, or pick an option above…` : composerProps.placeholder}
            onTextChange={(text) => {
              setDraft(text)
              composerProps.onTextChange?.(text)
            }}
          />
        </div>
      </div>
    </div>
  )
}
