import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EventRow } from '@/components/activity/EventRow'

describe('activity event presentation', () => {
  it('does not repeat an unrecognised event type as its own summary', () => {
    render(
      <EventRow
        event={{
          type: 'run_completed',
          data: {},
          timestamp: new Date().toISOString(),
          localId: 1,
        }}
        actorName="fixture"
      />,
    )

    expect(screen.getAllByText('run_completed')).toHaveLength(1)
  })
})
