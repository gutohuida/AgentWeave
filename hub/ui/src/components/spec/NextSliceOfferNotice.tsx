import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import {
  offerTitle,
  useDeclineNextSliceOffer,
  useNextSliceOffers,
  useTakeNextSliceOffer,
} from '@/api/nextSlice'

/**
 * The open document's next-slice offer, on today's header (`amendments-main-watch-and-the-next-
 * slice`, D6): once a roadmap slice's work is built, drafting the next slice is offered, never
 * queued. Draft queues one turn to the chosen agent (the document's author preselected); Not now
 * hides the offer for that slice. Renders nothing while there is no offer.
 */
export function NextSliceOfferNotice({ path }: { path: string }) {
  const { data: offers = [], error: offersError } = useNextSliceOffers()
  const { data: agents = [], error: agentsError } = useAgents()
  const take = useTakeNextSliceOffer()
  const decline = useDeclineNextSliceOffer()
  const offer = offers.find((entry) => entry.document === path)
  const [chosen, setChosen] = useState<string | null>(null)
  if (offersError) {
    // Said, not shown as "no offer": the offer may be there and unread.
    return (
      <p className="aw-spec-message" data-tone="warn" data-testid="next-slice-offer-error">
        <span className="aw-spec-message-text">
          Could not read whether the next slice is offered: {readableApiError(offersError, 'the Hub did not answer.')}
        </span>
      </p>
    )
  }
  if (!offer) return null
  const names = agents.map((agent) => agent.name)
  const options = offer.agent && !names.includes(offer.agent) ? [offer.agent, ...names] : names
  const agent = chosen ?? offer.agent ?? options[0] ?? ''
  const busy = take.isPending || decline.isPending
  const failure = take.error ?? decline.error
  return (
    <div className="aw-spec-message" data-testid="next-slice-offer">
      <span className="aw-spec-message-text">
        {offerTitle(offer)} Its tasks are closed and no document claims the next slice yet.
      </span>
      <select
        aria-label="Agent that drafts the next slice"
        value={agent}
        disabled={busy}
        onChange={(event) => setChosen(event.target.value)}
      >
        {options.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
      <Button
        variant="primary"
        size="xs"
        disabled={busy || !agent}
        onClick={() => take.mutate({ path, agent })}
      >
        Draft
      </Button>
      <Button variant="ghost" size="xs" disabled={busy} onClick={() => decline.mutate({ path })}>
        Not now
      </Button>
      {agentsError && (
        <span className="w-full" style={{ color: 'var(--text-3)' }}>
          Could not load the agents ({readableApiError(agentsError, 'the Hub did not answer')}); Draft asks the
          document's author.
        </span>
      )}
      {failure && (
        <span role="alert" className="w-full" style={{ color: 'var(--red)' }}>
          {readableApiError(failure, 'The Hub refused this.')}
        </span>
      )}
    </div>
  )
}
