## ADDED Requirements

### Requirement: Text the operator did not write reaches a run without a file mention its harness would expand

The system SHALL deliver text that the operator did not write to an agent's run, and every prompt it gives a one-shot worker, in a form in which the harness attaches no file for it.

Some harnesses read a file named by a mention token in a turn's input, such as `@path`, before the
model runs and without a tool call. A read made that way is never put to any permission posture.
Text written by another agent, a scheduled job, a checkpoint or any other source that is not the
operator therefore reaches a run with every such mention neutralised. The text also carries a
statement, in words and with no mention of its own, of how it was changed.

Only the text handed to the runner SHALL be changed. What the system stores and shows the operator
keeps the text as it was written. The exception is a message the operator sends that the system
composes around text an agent wrote (below): it is neutralised where it is composed, and stored as
delivered.

What the operator writes to an agent directly SHALL reach the run unchanged: a message from the
composer or the chat, and an answer the operator typed to a question. The operator's own mentions are
how they attach workspace files to a turn.

A scheduled job's firing SHALL be neutralised as a whole, including a message the operator wrote for
the job. A firing joins the job's message to text agents wrote (task titles and descriptions, a prior
checkpoint) in one text, and no job editor offers the operator a mention picker.

Every source other than the operator's direct messages SHALL be treated as not written by the
operator, including a source added later, until it is decided otherwise.

An answer to an agent's question is delivered together with the question. The question's text SHALL
be neutralised. An answer the operator gave by choosing one or more of the question's offered options
SHALL be neutralised too, because each option's text is the asking agent's. Where an answer carries
chosen options and any other text, the whole answer SHALL be neutralised.

A message the operator sends that the system composes around text an agent wrote, such as a request
to start work on a task an agent titled, SHALL carry that text neutralised. Text the system adds to a
turn that names something an agent can name, such as the path of the document open in a
specification turn, SHALL be neutralised in the same way and SHALL carry the same statement.

A mention the operator inserts by choosing from a list the system offers SHALL carry no second
mention of its own: a listed value that would carry one SHALL NOT be offered. This requirement does
not decide which file a listed path resolves to. A link inside the workspace that points outside it
is listed, and attaches its target, like any other path; that is tracked separately.

A one-shot worker, such as the one that writes a checkpoint or titles a conversation, SHALL have
every mention in its prompt neutralised, including the operator's. No worker attaches files that
way. A worker's output that the system stores SHALL NOT carry the neutralisation, whatever the worker
wrote. A check that compares a worker's answer with the system's records SHALL give the same
result whether or not the answer carries it.

#### Scenario: A peer's mention of a file outside the workspace attaches nothing

- **WHEN** an agent sends another agent a message that mentions a file outside the recipient's workspace in the harness's mention syntax
- **THEN** the recipient's harness attaches no file for that mention
- **AND** the recipient's turn states that text not written by the operator was changed so it cannot attach files

#### Scenario: The operator's own mention still attaches

- **WHEN** the operator sends an agent a message from the composer that mentions a workspace file in the harness's mention syntax
- **THEN** the message reaches the run unchanged and the harness attaches the file

#### Scenario: One turn mixes the operator's text and a peer's

- **WHEN** a single turn delivers an operator message and a peer message, each containing a mention
- **THEN** only the peer message's mention is neutralised

#### Scenario: An agent's own question does not come back as a file read

- **WHEN** the operator types an answer to a question whose text contains a mention
- **THEN** the question's text is neutralised in the delivered answer

#### Scenario: An answer the operator typed is not neutralised

- **WHEN** the operator answers a question by typing text that contains a mention, choosing no option
- **THEN** the answer reaches the run unchanged

#### Scenario: An answer that is an offered option attaches nothing

- **WHEN** an agent asks a question offering an option whose text mentions a file outside its workspace, the operator chooses that option, and the answer is delivered to the agent as queued input
- **THEN** the agent's harness attaches no file for that mention
- **AND** the question keeps its options and the chosen answer as they were recorded

#### Scenario: An answer that mixes chosen options with other text is neutralised whole

- **WHEN** an answer is recorded with one or more chosen options and answer text that differs from them
- **THEN** every mention in the delivered answer is neutralised

#### Scenario: A scheduled job's own message is neutralised

- **WHEN** a job whose message the operator wrote, containing a mention, fires
- **THEN** the job's message reaches the run with that mention neutralised
- **AND** the stored job keeps its message as written

#### Scenario: The stored message keeps its original text

- **WHEN** a peer message containing a mention is neutralised for delivery
- **THEN** the stored message and the operator's view of it show the text as the peer wrote it

#### Scenario: A checkpoint written from a conversation that mentions a file reads nothing

- **WHEN** an agent's output in a conversation mentions a file outside its workspace, and a checkpoint is then written for that conversation
- **THEN** the checkpoint worker's harness attaches no file for that mention
- **AND** the stored checkpoint does not contain the file's contents

#### Scenario: A changed file whose path contains an at-sign still passes the checkpoint probe

- **WHEN** a checkpoint lists a changed file whose path contains an at-sign, and the probe answers with that path as it was shown
- **THEN** the probe does not report the path as missing or invented

#### Scenario: Starting work on a task an agent titled attaches nothing

- **WHEN** an agent creates a task whose title mentions a file outside the workspace, and the operator starts an agent's work on that task from the board
- **THEN** the started agent's harness attaches no file for that mention
- **AND** the task keeps its title as the agent wrote it

#### Scenario: The open document's path attaches nothing

- **WHEN** a specification turn names the path of the document it is written to, and that path contains an at-sign
- **THEN** the turn names the path with its at-signs neutralised and states how it was changed
- **AND** the harness attaches no file for it

#### Scenario: A listed path that would carry a second mention is not offered

- **WHEN** the workspace holds a file whose path contains an at-sign that neither begins the path nor follows a `/`
- **THEN** neither the composer's mention trigger nor the file's detail tab offers to insert it as a mention

#### Scenario: A worker that copies the neutralisation does not store it

- **WHEN** a checkpoint worker's answer repeats a neutralised mention exactly as it was shown
- **THEN** the stored checkpoint shows the mention as originally written
