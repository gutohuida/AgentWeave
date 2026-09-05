## ADDED Requirements

### Requirement: A conversation carries the facts of the runs it renders
A chat history response SHALL carry a map of run facts keyed by `run_id` covering every run its own returned entries name, obtained by looking those runs up by id rather than by any query whose coverage depends on an ordering, a limit, or a different response's window.

The turns a client draws are its entries grouped by `run_id`, so the entries are what decide which
runs need facts. A response that returns the entries and not the facts leaves the client to find
them somewhere else, and every other place is scoped or bounded differently: an agent-wide event
window is not a conversation, and a fixed number of events is not the number of turns.

Coverage is therefore a property of the construction. The ids come from the entries the response is
returning, after every truncation that response applies and after any still-undelivered entries are
appended, and the runs are read by primary key. There is no bound that could be chosen too small and
no window either side to fall out of.

This holds for a response scoped to one conversation and for a response spanning an agent's recent
activity across conversations. Both draw turns; both must carry the facts of the runs those turns
name.

A run named by an entry whose row genuinely cannot be found is omitted from the map, and the client
presents that turn exactly as it presents a run with no outcome yet.

#### Scenario: The map covers the turns the response returns

- **WHEN** a client requests a conversation's history and the returned entries name any number of
  distinct runs
- **THEN** every one of those runs whose row exists is present in the response's run facts map

#### Scenario: Work in another conversation does not erase an outcome

- **WHEN** a turn in one conversation ended, and the agent afterwards runs any number of turns in
  other conversations
- **THEN** the first conversation's response still carries that run's facts, because what the
  agent did elsewhere is not one of the things its coverage depends on

#### Scenario: The conversation's outcomes are read from the response that carried its turns

- **WHEN** a client presents a turn's outcome
- **THEN** the facts it presents come from the same response as the entries that turn was grouped
  from, and not from any other response that also happens to carry a run facts map

#### Scenario: A long conversation keeps its oldest outcomes

- **WHEN** one conversation holds more finished turns than any fixed event window would return
- **THEN** every turn the response returns presents its own outcome, including the oldest

#### Scenario: The agent-wide recent view carries its own facts

- **WHEN** a client requests an agent's recent activity across conversations rather than one
  conversation
- **THEN** the response carries the facts of the runs its own returned entries name

#### Scenario: An unknown run degrades rather than fails

- **WHEN** a returned entry names a `run_id` that has no row
- **THEN** the map omits that key and the client presents that run exactly as it presents a run with
  no outcome yet

#### Scenario: The map does not cross a project boundary

- **WHEN** the run facts for a response are read
- **THEN** the lookup is constrained to the project the response belongs to, so no run from another
  project can enter the map

### Requirement: A run ending refreshes the conversation that renders it
A client displaying a conversation SHALL refresh that conversation's run facts when a run for that agent reaches a terminal status and when the client's event stream reconnects after an interruption, rather than only when new conversation content arrives.

A turn's outcome is now carried by the same response as its entries, so whatever causes that
response to be re-read is what causes the outcome to appear. Content arriving is not sufficient:
a run whose end the Hub did not observe produces no output row at all, and a client waiting for one
waits forever while the run's row already records how it ended.

Two signals, because one run-ending is not observable by the client at all. A run reconciled at Hub
restart has its status decided while the client is disconnected — the process that broadcasts the
event is the process the client's stream died with — and a broadcast with no subscriber is not
delivered later. The reconnect is the only moment at which such a client can learn anything, so the
rule is stated over the reconnect and not over the event, and a client that listened only for the
event would satisfy the letter of the terminal-status half while failing the case that motivates it.

A run *beginning* is deliberately not a refresh trigger. It changes nothing in the response that
the arrival of its output will not already carry, and refetching an unbounded history on that signal
costs more than it states.

#### Scenario: An interrupted run's outcome arrives without new content

- **WHEN** a run is recorded as interrupted at Hub restart, writing a lifecycle event and no output
  row, while an operator has that conversation open
- **THEN** the turn presents its terminal label without the operator reloading the page and without
  unrelated traffic arriving for that agent

#### Scenario: A decision made while the client was disconnected still reaches it

- **WHEN** a run's outcome is recorded at a moment when the client has no live event stream, so no
  event for it can be delivered
- **THEN** the conversation presents that outcome once the stream is back, without the operator
  reloading the page

#### Scenario: A stopped run's outcome arrives on the run's own signal

- **WHEN** the operator stops a turn
- **THEN** the conversation presents the terminal label as a consequence of the run reaching a
  terminal status, not as a consequence of some later unrelated event

## MODIFIED Requirements

### Requirement: A run's terminal outcome is visible
The conversation SHALL show, for every run that ended, whether it completed, failed, was stopped or was interrupted, and SHALL show it again after a page reload.

A run whose row genuinely cannot be found is the only case that may present no outcome. That is
distinct from a run whose row exists but was omitted from the response the conversation reads, which
is a defect and is forbidden by *A conversation carries the facts of the runs it renders*.

That cross-reference used to name *The run facts cover every run the events name*, and naming it was
itself the hole. That requirement is quantified over the runs a returned **event** names, so it
cannot forbid omitting a run no returned event names — which is precisely what happens when a turn
is drawn from a conversation's entries while its outcome is sought in an agent-wide event window.
The rule that forbids it has to be stated over the response the conversation actually reads.

#### Scenario: A stopped run says it was stopped

- **WHEN** the operator stops a turn and the run's status becomes `stopped`
- **THEN** the turn presents a terminal label naming the stop, rather than ending with no statement

#### Scenario: The outcome survives a reload

- **WHEN** a conversation containing a stopped, failed or interrupted run is loaded fresh, with no
  live stream having delivered anything
- **THEN** that run's terminal label is presented from persisted state alone

#### Scenario: The outcome survives the agent working elsewhere

- **WHEN** a conversation containing a stopped, failed or interrupted run is loaded fresh, after the
  agent has done enough work in other conversations to fill any agent-wide window the client also
  reads
- **THEN** that run's terminal label and duration are presented unchanged

#### Scenario: A failed run is distinguishable from a silent one

- **WHEN** one run ended `failed` and another ended `completed` having produced no assistant text
- **THEN** the two turns present different terminal states rather than both presenting none

#### Scenario: A run still executing claims no outcome

- **WHEN** a run's status is `running`
- **THEN** no terminal label is presented for it

#### Scenario: A turn that produced nothing still reports what it cost

- **WHEN** a run ended without producing any visible agent output, so the only output row its turn
  carries is a terminal status row the conversation does not draw
- **THEN** the turn still presents its duration and token line, rather than losing it along with the
  row it was attached to
