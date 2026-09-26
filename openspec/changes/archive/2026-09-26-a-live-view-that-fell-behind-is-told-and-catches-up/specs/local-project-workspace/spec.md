## ADDED Requirements

### Requirement: A stream subscriber that falls behind is told what it lost
When the Hub drops events for a stream subscriber whose queue is full, that stream SHALL send one `stream_gap` frame carrying the number of events dropped as soon as it is sending again, and the app SHALL respond to it as it responds to a reconnect.

The Hub MAY keep dropping events for a slow subscriber rather than block other broadcasters, but it
MUST NOT drop them silently. A `stream_gap` frame is stream metadata, not a project's event: it
SHALL NOT carry a `project_id`, and the app SHALL refresh every project's server state on receiving
it. The Activity feed SHALL show a line saying events were not delivered, whatever project is
selected.

#### Scenario: A stalled subscriber is told how many events it missed
- **WHEN** an operator-stream subscriber stops reading, its queue fills, and ten more events are broadcast across two projects
- **THEN** once the stream is sending again it sends one `stream_gap` frame with `dropped` equal to 10 and no `project_id`
- **AND** no further gap frame is sent until more events are dropped

#### Scenario: A burst followed by silence is still reported
- **WHEN** a subscriber's queue overflows and no further event is broadcast
- **THEN** the gap frame is still sent once the queued events have been sent

#### Scenario: The app catches up after a gap
- **WHEN** the app receives a `stream_gap` frame
- **THEN** it invalidates all of its server state and runs the same reconciliation it runs after a reconnect
- **AND** the Activity feed shows that events were not delivered, even when another project is selected
