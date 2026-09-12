## ADDED Requirements

### Requirement: Giving up on queued input goes on to the input behind it

Where an attempt to start an agent's turn ends by giving up on the input that turn was built from, the system SHALL go on, in the same pass and without waiting for any other event, to attempt the input queued behind it, SHALL go on only after giving up, and SHALL count a delivery attempt against any one input at most once in a pass.

The system gives up on refused input at a limit so that input that can never be delivered stops
holding up the queue behind it (*"A delivery attempt is counted only where a delivery was
attempted"*). Giving up releases that queue only if something then tries it. Nothing re-evaluates
an agent on a timer. What does is a run ending, an operator acting on that agent, or an unrelated
repair. So a pass that gives up on the head of the queue and then stops is the last pass for that
agent until something else happens, and the input it released waits for as long as nothing does.
Where the input it released is a review the system has just staffed onto that same agent, the board
shows the review in progress and nothing is working on it.

The pass SHALL go on only where it gave up on input. It SHALL stop, as it does without this
requirement, where the attempt started a turn, where the refusal is one that clears on its own,
where the refusal prevents the agent from running at all, where a delivery attempt was counted and
the input was not given up on, and where there was nothing to attempt. Going on after any of those
would repeat the same refusal, or would spend the allowance of input nobody gave up on. Spending
that allowance in one pass destroys the input that the allowance exists to protect.

Going on only after giving up is not, by itself, enough to protect the input behind. Input rides in
a turn built from other input, so input that rode in the turn the system gave up on can be carried
again by the next attempt, and by the one after that. Counted each time, one pass could give up on
input that no pass before it had ever refused, which is the loss the allowance exists to prevent.
So a pass SHALL count each input at most once, however many of its attempts carry it, which is
what a pass that does not go on already does. The input is still attempted each time; only the
count is not raised again.

The pass SHALL end. Every attempt after the first follows the system giving up on input that was
already queued when the pass began. Input that arrives during the pass has had no attempts, so it
cannot be given up on in its first.

Where the pass goes on, a request SHALL be answered about the input it submitted, from the attempt
that carried that input: started where that attempt started it, refused where that attempt refused
it for what it asked, and waiting where it is still queued. Where going on found nothing left to
attempt, what the pass reports SHALL be the attempt that gave up, not the empty queue.

#### Scenario: The input behind given-up input is delivered in the same pass

- **WHEN** the input at the head of an agent's queue is refused for the last time its limit allows,
  and the system gives up on it
- **AND** other input for the same agent is queued behind it, in another conversation
- **THEN** the input behind it is delivered in a turn started by the same pass
- **AND** no other event was needed to start it

#### Scenario: Going on does not spend the next input's allowance

- **WHEN** the system gives up on the head of an agent's queue
- **AND** the input behind it is refused too
- **THEN** one delivery attempt is counted against the input behind it
- **AND** that input remains queued
- **AND** the pass stops

#### Scenario: Going on never counts one input twice in a pass

- **WHEN** input that no attempt has been counted against rides in a turn built from other input,
  and the system gives up on that other input
- **AND** the same pass carries the riding input again, in its next attempt, and that attempt is
  refused too
- **THEN** one delivery attempt in total is counted against the riding input in that pass
- **AND** the riding input remains queued

#### Scenario: A refusal that clears on its own does not make the pass go on

- **WHEN** the turn built from the head of an agent's queue is deferred for a reason that clears on
  its own
- **THEN** no other input for that agent is attempted in that pass
- **AND** no delivery attempt is counted against the head

#### Scenario: A pass over input that is all refused ends

- **WHEN** every input queued for an agent is at the last attempt its limit allows
- **AND** each is refused in turn
- **THEN** the system gives up on each of them once
- **AND** the pass ends

#### Scenario: A request queued behind given-up input is answered as started

- **WHEN** the operator submits input to an agent whose queue holds older input in another
  conversation
- **AND** the pass that request triggers gives up on the older input and then starts a turn
  carrying the operator's input
- **THEN** the request is answered as started, in the conversation it submitted to

#### Scenario: A pass that gave up on the last input reports the refusal, not an empty queue

- **WHEN** the pass gives up on the only input queued for an agent
- **THEN** what the pass reports is that input's refusal
- **AND** it does not report that the queue was empty
