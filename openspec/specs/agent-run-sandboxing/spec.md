# agent-run-sandboxing

## Purpose

Defines the sandbox posture the Hub imposes on a spawned agent run, independent of whatever
configuration happens to exist on the machine the Hub process runs on. Originated by
`openspec/changes/2026-08-06-claude-non-yolo-permission-mode`.
## Requirements
### Requirement: A non-yolo Claude run's sandbox posture is set by the Hub, not the host machine

The Hub SHALL pass an explicit, non-bypass permission mode to every non-yolo Claude run it spawns. A
non-yolo Claude run's actual permission behavior MUST NOT depend on the config file of the machine the
Hub process happens to run on.

#### Scenario: Non-yolo Claude run gets an explicit permission mode

- **WHEN** the Hub spawns a Claude agent whose run is not `yolo`
- **THEN** the spawned command line includes an explicit non-bypass permission mode flag

#### Scenario: Yolo Claude run is unaffected

- **WHEN** the Hub spawns a Claude agent whose run is `yolo`
- **THEN** the spawned command line includes `--dangerously-skip-permissions`
- **AND** does not include the non-yolo permission mode flag

### Requirement: A sandboxed non-yolo Claude agent can still use the Hub's own MCP tools

When a non-yolo Claude run has the Hub's own MCP server configured, the Hub SHALL allowlist that
server's tools explicitly, so the agent's general sandbox does not also block AgentWeave's own tooling.

#### Scenario: Hub's own MCP tools remain usable under the sandbox

- **WHEN** the Hub spawns a non-yolo Claude agent with its own MCP server configured
- **THEN** the spawned command line allowlists that server's tools
- **AND** an action outside that allowlist is still refused

#### Scenario: No allowlist is added when there is nothing to allowlist

- **WHEN** the Hub spawns a non-yolo Claude agent with no MCP server configured
- **THEN** the spawned command line does not include an MCP tool allowlist flag

### Requirement: The default posture lets an agent work inside its own workspace

The permission posture the Hub imposes by default SHALL permit an agent to do work within its own
workspace without further configuration.

The Hub MUST NOT impose by default a posture whose decisions can only be resolved by an operator
prompt, unless a surface exists through which an operator can actually answer that prompt. A posture
that defers every decision to an absent answerer denies everything and is indistinguishable from a
broken run.

Isolation SHALL continue to be carried by the agent's workspace boundary, not by withholding
permission inside it.

#### Scenario: A newly created agent can edit files in its own workspace

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** that agent writes a file inside its own workspace
- **THEN** the write succeeds
- **AND** no approval was required from an operator

#### Scenario: A posture requiring an answer is not imposed by default

- **WHEN** no operator-facing approval surface exists for a provider
- **THEN** the Hub does not default that provider's runs to a posture that asks for approval

#### Scenario: The workspace boundary is unchanged

- **WHEN** an agent acts under the default posture
- **THEN** its ability to affect anything outside its own workspace is unchanged by that posture

### Requirement: The operator chooses a conversation's permission posture

The operator SHALL be able to select the permission posture used for a conversation's runs, from the
postures the provider supports, and that selection SHALL take effect on the next run of that
conversation.

The selection MUST reach the spawned command. A control that is displayed but does not change what
the run receives is a defect, not a cosmetic issue.

Postures SHALL be presented in terms of what they allow, not by the provider's internal flag spelling.

#### Scenario: A selected posture reaches the run

- **WHEN** the operator selects a permission posture for a conversation and sends a message
- **THEN** the spawned command carries that posture
- **AND** does not also carry the default posture

#### Scenario: Selecting the most restrictive posture restores refusals

- **WHEN** the operator selects the posture that requires approval for every action
- **AND** the agent attempts a write
- **THEN** the write does not succeed

#### Scenario: A posture is described by what it permits

- **WHEN** the permission postures are presented to the operator
- **THEN** each is labelled by the access it grants rather than by its provider flag value

### Requirement: A posture exists in which the workspace boundary is enforced per tool call

The Hub SHALL offer a permission posture under which each of a run's tool calls is decided against
the run's own workspace, rather than permitted in advance.

Under that posture a tool call confined to the run's workspace is allowed, and one reaching outside
it is refused with a reason stating what was refused and why. The comparison SHALL be made on fully
resolved paths, so that a relative traversal or a symbolic link cannot escape a boundary that an
unresolved comparison would have accepted.

The boundary enforced SHALL be the same one the agent is told it is working in. A boundary that is
described in one place and enforced from another can disagree, and the agent is given no way to tell
which is real.

Where the boundary cannot be established, the posture SHALL refuse rather than permit. An
unknown boundary is not an absent one.

#### Scenario: Work inside the workspace proceeds

- **WHEN** a run under this posture acts on a path inside its own workspace
- **THEN** the action is allowed

#### Scenario: Work outside the workspace is refused with a reason

- **WHEN** a run under this posture acts on a path outside its own workspace
- **THEN** the action is refused
- **AND** the refusal states what was refused and why

#### Scenario: Traversal and links cannot escape

- **WHEN** a path reaches outside the workspace only after relative traversal or link resolution
- **THEN** it is refused

#### Scenario: An unestablished boundary refuses

- **WHEN** the run's workspace cannot be determined
- **THEN** actions under this posture are refused

#### Scenario: Collaboration is not a filesystem decision

- **WHEN** a run under this posture uses the Hub's own tools
- **THEN** those calls are allowed

---

### Requirement: Every permission decision is answered, and answering never depends on the Hub

The Hub SHALL answer every permission request a run raises, including requests whose shape it does
not recognise, for which the answer is refusal.

A decision SHALL be reached without requiring a response from any other process. An unanswered
request does not fail a run, it suspends it indefinitely, so a decision path that can time out, be
refused a connection, or wait on a restart is a decision path that can hang a turn forever.

#### Scenario: An unrecognised request is answered

- **WHEN** a permission request is raised whose shape is not recognised
- **THEN** it is refused rather than left unanswered

#### Scenario: Decisions survive an unavailable Hub

- **WHEN** the Hub cannot be reached while a run is deciding a permission request
- **THEN** the request is still answered

---

### Requirement: A refused action is visible to the operator

Where a run's action is refused by the enforced boundary, the Hub SHALL make that refusal visible to
the operator.

An agent that is silently refused appears merely to have chosen differently. The operator is the only
participant who can widen a boundary or redirect the work, and cannot do either without knowing a
refusal happened.

Reporting a refusal MUST NOT alter or delay the decision it reports. Visibility is an observation of
a decision already reached, never a precondition of reaching it.

#### Scenario: A refusal reaches the operator

- **WHEN** an action is refused under the enforced boundary
- **THEN** the operator can see that the refusal happened

#### Scenario: Failed reporting changes nothing

- **WHEN** a refusal cannot be reported
- **THEN** the decision is unchanged
- **AND** the run continues

---

### Requirement: Introducing an enforced posture does not change existing runs

The default posture SHALL NOT change as a consequence of an enforced posture becoming available, and
runs that do not select it SHALL be spawned exactly as before.

A posture that decides each tool call is new machinery on the path of every action. Adopting it is a
deliberate choice, made per conversation, not a change imposed on every existing agent's next run.

Flags that serve the enforced posture SHALL be emitted only for that posture, and only where the
mechanism answering them is present.

#### Scenario: The default is unchanged

- **WHEN** a non-yolo run is spawned with no posture selected
- **THEN** it uses the same default posture as before the enforced posture existed

#### Scenario: Other postures carry no enforcement machinery

- **WHEN** a run selects a posture other than the enforced one
- **THEN** its command carries nothing referring to the enforcement mechanism

#### Scenario: No enforcement is claimed without an answerer

- **WHEN** the enforced posture is selected but no mechanism is present to answer its requests
- **THEN** the command does not claim enforcement it cannot perform

### Requirement: A permission request does not outlive the wait it represents

A permission request SHALL reach a terminal status whenever the run that raised it stops waiting —
by answering, by timing out, by being stopped, or by ending for any other reason. It SHALL NOT
remain pending once nothing is waiting on it.

Reaching that terminal status SHALL NOT depend on the run successfully reporting it. A run that is
killed, crashes, or cannot reach the Hub still stops waiting, and the request SHALL still be closed.

Reporting that a wait has ended MUST NOT alter or delay the decision the run already reached. As with
reporting a refusal, this is an observation of something already true.

#### Scenario: A request whose wait timed out is closed

- **WHEN** a run's wait for an operator decision runs out
- **THEN** the request reaches a terminal status rather than remaining pending

#### Scenario: A request outliving its run is closed

- **WHEN** a run ends while a permission request it raised is still pending
- **THEN** that request reaches a terminal status

#### Scenario: A killed run's request is still closed

- **WHEN** a run is stopped or dies without reporting that its wait ended
- **THEN** its pending permission requests are still closed

#### Scenario: Closing twice is harmless

- **WHEN** a request's wait is reported as ended after the request has already been closed
- **THEN** the request is unchanged and no error is surfaced to the run

### Requirement: A decision is refused once nobody is waiting for it

The Hub SHALL refuse an operator decision on a permission request that is no longer pending, and
SHALL say that the run has moved on.

An accepted decision is a record that the operator authorised an action. Recording an approval for a
call that already proceeded without it — or was already refused — states an authority that was never
exercised, which is worse than refusing the decision outright.

#### Scenario: Deciding a closed request is refused

- **WHEN** an operator submits a decision for a request that has already reached a terminal status
- **THEN** the decision is refused and the operator is told the run has moved on

#### Scenario: A refused decision does not alter the record

- **WHEN** a decision on a closed request is refused
- **THEN** the request's status, decision time, and decider are unchanged

### Requirement: The operator can see that an agent stopped waiting

A permission request that ended without an operator decision SHALL remain visible to the operator and
SHALL be presented as expired, distinctly from one they answered.

The operator is the only participant who can widen the wait or be present for the next one, and
cannot do either without learning that an agent gave up. A request that disappears silently withholds
exactly that.

An expired request SHALL NOT be answerable.

#### Scenario: An expired request is shown as expired

- **WHEN** a permission request expires without an operator decision
- **THEN** it remains visible to the operator, marked as expired rather than removed

#### Scenario: An expired request offers no decision

- **WHEN** the operator views an expired permission request
- **THEN** it presents no way to allow or deny it

#### Scenario: An expired request is distinguishable from an answered one

- **WHEN** the operator views a permission request that expired and one they decided
- **THEN** the two are visibly different

### Requirement: The operator can clear an expired request they have seen

The Hub SHALL let the operator dismiss an expired permission request, after which it is no longer
presented to them. Dismissing SHALL NOT change what the agent was told or who authorised what.

Expired requests accumulate deliberately, because a run of missed decisions is something the
operator should see building up. A pile that cannot be cleared stops being a signal, so
acknowledgement has to be possible without pretending a decision was made.

A request that is still pending SHALL NOT be dismissable. The run is still waiting on it, and
clearing it from view would refuse it by neglect while appearing to be housekeeping.

#### Scenario: An expired request is cleared once seen

- **WHEN** the operator dismisses an expired permission request
- **THEN** it is no longer presented to them, and its status and decision record are unchanged

#### Scenario: A request still being waited on cannot be cleared

- **WHEN** the operator attempts to dismiss a request that is still pending
- **THEN** the attempt is refused, and the request remains presented for a decision

#### Scenario: Dismissing twice is harmless

- **WHEN** an already-dismissed request is dismissed again
- **THEN** it is unchanged and no error is surfaced

### Requirement: A refusal is recorded wherever it is decided

The system SHALL record a durable event when it refuses an agent's action, regardless of which runtime decided the refusal.

An operator reading the activity of a run needs to know an agent was blocked. A refusal that exists
only in the agent's own prose account is one the operator will not find, and the agent's summary of
its own failure is a claim rather than a record.

Recording SHALL cover refusals a runtime decides on its own, not only those the operator was asked
about. The refusals an operator never saw are precisely the ones they cannot otherwise learn of.

A refusal SHALL be recorded once. A decision the operator already answered is already recorded, and
recording it again tells them it happened twice.

Only refusals SHALL be recorded **as refusals**. An allowed action is the ordinary case, and a
refusal record with an entry per allowed action buries the refusals among them. This constrains
what the refusal record may contain; it is not a rule about every durable event the system keeps.

The recorded event SHALL name the refused action in terms the operator can read.

#### Scenario: A runtime refuses an action on its own

- **WHEN** a runtime refuses an agent's action without asking the operator
- **THEN** the refusal appears in the project's activity

#### Scenario: An operator-answered refusal is recorded once

- **WHEN** the operator is asked about an action and refuses it
- **THEN** exactly one refusal is recorded

#### Scenario: Allowed actions are not recorded as refusals

- **WHEN** a runtime allows an agent's action
- **THEN** no refusal is recorded

#### Scenario: The refused action is readable

- **WHEN** a refusal is recorded
- **THEN** the action it names is readable rather than an internal method name

### Requirement: A file tool writing outside the run's workspace is recorded, in every posture

The Hub SHALL record, against the run, every call to a file-writing tool whose target resolves outside that run's own workspace, in every permission posture, including postures that perform no check and postures in which the operator approved the call.

Detection SHALL be made where the run's tool calls are already observed to build its transcript, not
where they are approved. Approval runs in some postures and not others, and under the posture in
which the operator answers, the call being recorded is one they deliberately allowed. Observation
runs in all of them, because it is how the run is rendered at all.

The boundary compared against SHALL be the run's own recorded workspace — the same value the run was
started in and the same value any enforcing posture checks. A second boundary computed from the
agent's identity would be able to disagree with the first, and nothing could then say which is real.

The record SHALL name **which workspace was written into**, as a kind and a name, and not merely that
the write left the run's own. The destinations are distinguishable and they do not mean the same
thing. A write into another agent's or task's workspace is committed onto that workspace's branch by
the Hub's own snapshot, under a subject naming its owner's turn, and thereafter flows through review,
evidence and integration attributed to the wrong actor. A write into the project's tracked tree lands
where its owner's `git status` will show it.

**The Hub's own working directory under the project root SHALL be a destination kind of its own, and
SHALL NOT be reported as the project's directory.** The Hub seeds the repository's ignore rules with
its own subtree on every turn, so a write there is the one part of the project root that is
deliberately invisible to `git status` — the opposite of the tracked case above — and part of it is
the Hub's own record-keeping about the very run doing the writing. Naming it "the project" would
attach the mildest reading to the least visible destination.

The record SHALL be bounded, and repeated writes to the same destination within one run SHALL notify
the operator once rather than once per call.

Where the run's workspace cannot be established or resolved, nothing SHALL be recorded, and the
absence SHALL NOT be reported as a write outside the workspace. This differs deliberately from the
enforcing posture, which refuses when it cannot establish a boundary: refusing is correct for a gate,
whereas writing "it wrote outside" when the truth is "nobody could tell" would attribute to an agent
something it may not have done.

A run for which no observation was made SHALL be distinguishable from a run observed and found to
have written nothing outside its workspace.

The record SHALL NOT be a refusal and SHALL NOT be presented as one. The action it describes was
allowed — by an operator who answered for it, or by a posture that checked nothing — and a record
that reads as a refusal would tell the operator the write did not land when it did.

**A run whose workspace is the project's own directory is outside this requirement's reach, and the
absence of a record for it SHALL NOT be read as confinement.** Where the run's workspace and the
project directory are the same — a read-only agent, a project that is not a repository, a machine
with no git — every path inside the project is inside that run's workspace, including another
agent's checkout. Such a run is correctly recorded as having written nothing outside its workspace,
because its workspace is everything; it is also the least confined run the product has. The two
readings are only compatible while the recorded directory is read as *where the run started*, which
is what the companion requirement in `workspace-isolation` establishes.

**Scope is part of the requirement, not a limitation of it.** What is recorded is that a file tool
wrote outside the workspace. It SHALL NOT be described, labelled or surfaced as a complete account of
writes leaving the workspace, because two vectors are not reachable from a check on a tool call's
declared path and are out of scope:

- a shell command, which carries a command string rather than a path argument, so a redirect to an
  absolute path names no path this check can see;
- a symbolic link inside the workspace pointing outside it, whose reported path is legitimately
  inside.

A detector that misses the case it is named for is worse than none, because it reads as coverage.
Named for exactly what it catches, it is coverage.

#### Scenario: A write outside the workspace under the default posture

- **WHEN** a run's file-writing tool call names a path outside the run's workspace
- **THEN** the call is recorded against the run
- **AND** the record names the tool, the path, and the workspace the path belongs to

#### Scenario: An operator-approved write outside the workspace is still recorded

- **WHEN** a run under the posture in which the operator answers makes a file-writing call outside its
  workspace and the operator allows it
- **THEN** the write is recorded against the run
- **AND** the record does not depend on how the call was decided

#### Scenario: A posture that checks nothing is still observed

- **WHEN** a run under a posture that performs no permission check writes outside its workspace
- **THEN** the write is recorded against the run

#### Scenario: A write into another workspace names that workspace

- **WHEN** a run writes into a workspace belonging to another agent or to a task
- **THEN** the record names that workspace's kind and name
- **AND** does not merely state that the write was outside the writing run's own

#### Scenario: Work inside the workspace is not recorded

- **WHEN** a run's file-writing calls all resolve inside its own workspace
- **THEN** no such record is made
- **AND** the run is still distinguishable from one that was never observed

#### Scenario: A relative path that traverses outside is caught

- **WHEN** a file-writing call names a relative path that resolves outside the workspace only after
  traversal
- **THEN** it is recorded as a write outside the workspace

#### Scenario: The record is not a refusal

- **WHEN** a write outside the run's workspace is recorded
- **THEN** the record is not a refusal
- **AND** it does not claim the action was refused or prevented

#### Scenario: A run whose workspace is the project directory records nothing

- **WHEN** a run's workspace is the project's own directory and it writes anywhere inside the project
- **THEN** no write outside the workspace is recorded
- **AND** the empty record is not a statement that the run was confined

#### Scenario: Reads are not recorded

- **WHEN** a run reads a file outside its workspace
- **THEN** nothing is recorded

#### Scenario: An unestablished workspace records nothing

- **WHEN** a run's workspace cannot be established or resolved
- **THEN** no write is recorded for that run
- **AND** the run is not reported as having written outside its workspace

#### Scenario: Repeated writes to one destination notify once

- **WHEN** a run makes several file-writing calls into the same destination workspace
- **THEN** every call is present in the run's record
- **AND** the operator is notified once for that destination rather than once per call

### Requirement: The product states which postures confine a run and which do not

The Hub's documentation SHALL state, per permission posture, whether a run's file writes are checked against its workspace, and SHALL NOT state it per execution mode.

Saying it by mode would be false in both directions. In native mode the posture in which the Hub
answers each call *does* refuse a path outside the run's workspace, so telling an operator running the
default that nothing is checking is wrong; and the postures that check nothing exist in native mode
too, so telling an operator running one of those that native mode's story applies to them is equally
wrong. Docker mode confines at the mount, by construction, whatever posture is selected.

The statement SHALL say that a workspace is a working directory rather than a wall, that the operator
is the boundary where no posture is checking, and that a write that leaves the workspace is recorded
rather than prevented.

#### Scenario: The postures are documented by what they check

- **WHEN** the permission postures are documented
- **THEN** each states whether a file write is checked against the run's workspace

#### Scenario: Containment is not claimed for a mode

- **WHEN** the documentation describes native execution
- **THEN** it does not claim that native mode confines a run's writes
- **AND** it does not claim that native mode leaves them entirely unchecked

### Requirement: A network address in a shell command is decided as a network address

Under the posture in which the Hub decides each tool call against the run's workspace, a shell command that names a network address SHALL be allowed only when that address is the run's own Hub, and SHALL otherwise be refused with a reason that names network access rather than the workspace or the filesystem.

A network address is not a path, and reading one as a path produces a refusal for a false reason.
Until this requirement, the posture read `https://example.com/x` as the Windows drive path
`s://example.com/x`, and read the path after `$HUB_URL` as a path at the root of the drive. Both
were refused as *outside your workspace*. That sent the model and the operator to debug a filesystem
about a request that never touched one, and it refused the one request the Hub itself instructs a
run to make.

The run's own Hub is the address the Hub placed in the run's environment. A command may name it
literally, where scheme, host and port all match and no user information is present, or by
reference to the environment variable that holds it. A reference is trusted only when the command
names that variable nowhere else. A command that assigns the variable and then uses it names
whatever it assigned. Two host names that may resolve to the same machine are not treated as the
same address.

Allowing the run's own Hub as an address does not allow it as a path. The shell does not know that
a word is an address, and a command can write to one as a relative path. That path's `..`
segments can climb out of the workspace. So a word accepted as the run's own Hub is still judged as
the path it spells. A request to the Hub has no need of such a segment.

**This is a rule about what a shell command's text names. It is not containment of network
access, and the refusal SHALL NOT claim that it is.** A command can reach a network without writing
an address down, and tools whose input is an address are decided separately. A refusal that says
the network is unavailable would be false. The reason says what this rule does: which address a
shell command may name.

The refusal SHALL name the way out: asking the operator. An agent refused with nothing it can do,
that still has a task to finish, is left to find another route, and at this layer another route is
one line long.

This requirement governs the decision the Hub makes by reading a shell command's text. A runner
whose command approvals the Hub decides by working directory alone is not brought under it by this
requirement.

#### Scenario: The run's own Hub is reachable from a shell command

- **WHEN** a run under this posture runs a shell command that names its own Hub's address, either
  literally or by the environment variable that holds it
- **THEN** the command is allowed

#### Scenario: The run's own Hub address does not carry a path out of the workspace

- **WHEN** a shell command names the run's own Hub address followed by enough `..` segments that,
  read as a relative path, it resolves outside the workspace
- **THEN** the command is refused

#### Scenario: An address that only resembles the run's own Hub is refused

- **WHEN** a shell command names an address that differs from the run's own Hub in scheme, host or
  port, or that carries user information
- **THEN** the command is refused as a network address

#### Scenario: A reassigned reference is not trusted

- **WHEN** a shell command refers to the variable holding the Hub's address and also names that
  variable in any other way
- **THEN** the reference is not treated as the run's own Hub

#### Scenario: Another network address is refused for a network reason

- **WHEN** a run under this posture runs a shell command naming any other network address
- **THEN** the command is refused
- **AND** the reason states that the refused word is a network address
- **AND** the reason does not state that it is outside the workspace
- **AND** the reason names asking the operator as the way to proceed

#### Scenario: The refusal does not claim containment

- **WHEN** a shell command is refused as a network address
- **THEN** the reason does not state that network access is unavailable to the run

#### Scenario: A file URL is a path

- **WHEN** a shell command names a URL whose scheme addresses the local filesystem
- **THEN** it is judged as the path it names, not as a network address

### Requirement: A path in a shell command is judged by where it resolves

Under the posture in which the Hub decides each tool call against the run's workspace, each path in a shell command SHALL be judged by where it resolves against the run's workspace, as the shell that runs the command will read it, and a refusal SHALL name the whole path, not a fragment of it.

A shell command carries no declared path argument, so its paths are read out of its text. Reading
them out of the middle of words produced two opposite errors from one mechanism. A file in a
subdirectory of the workspace, such as `sub/hello.py`, was read as `/hello.py` at the root of the
drive and refused as outside. And a traversal out of the workspace, `../stray.txt`, was refused
only because the same misreading happened to land outside. The first refused ordinary work inside
the boundary. The second held the boundary for a reason that named a path nobody wrote.

A relative path is judged by resolving it against the workspace, so a traversal that leaves the
workspace is refused as what it is.

The path judged is the one the shell will produce, not the text as typed. A shell removes quotes
and escapes and joins what stands on either side of them, so a command can assemble a traversal
from pieces that each look harmless. Which characters are removed, and whether a backslash escapes
or separates, depends on the shell. So the command is read in the dialect of the tool that carries
it. Where that dialect is not known, the command is read every way the product supports, and a
refusal under any reading refuses it.

Dividing a command into the words it names can end a word at a name the shell then carries on. A
workspace-relative path that ends at the workspace's own name, followed by more characters, names
a sibling of the workspace. Such a word SHALL be judged as the name it continues into.

A word whose destination the shell decides only when it runs cannot be checked. That covers a word
that contains a variable or a command substitution, or begins with the home-directory shorthand,
and that also contains a path separator. Such a word SHALL be refused with a reason saying it cannot
be checked. It SHALL NOT be refused with a reason claiming it is outside the workspace, and it
SHALL NOT be allowed on the grounds that nothing visible in it points outside.

A word that joins a path to something else, such as an option, a prefix character, or a host, SHALL
be judged at least as strictly as the path within it would be if it stood alone. Reading words from
their start must not let through a path that reading them from the middle refused.

Where the platform accepts more than one path separator, each is a separator in the path the shell
passes on.

Where a path cannot be resolved at all, the call SHALL be refused, and the request SHALL still be
answered. An error in place of an answer is not a decision.

#### Scenario: A file in a subdirectory of the workspace

- **WHEN** a run under this posture runs a shell command naming a relative path inside a
  subdirectory of its own workspace
- **THEN** the command is allowed

#### Scenario: A relative traversal out of the workspace is refused as written

- **WHEN** a shell command names a relative path that resolves outside the workspace after
  traversal
- **THEN** the command is refused
- **AND** the reason names the whole path, not a fragment of it

#### Scenario: A traversal assembled from quoted pieces is judged as assembled

- **WHEN** a shell command writes a path from pieces that the shell joins by removing quotes or
  escapes between them, and the joined path resolves outside the workspace
- **THEN** the command is refused

#### Scenario: A word that runs on past the workspace's own name is judged as it runs on

- **WHEN** a word of a shell command resolves to the workspace itself, and the shell's argument
  continues that word's last name into the name of a sibling of the workspace
- **THEN** the command is refused

#### Scenario: A path the shell builds when it runs is refused as uncheckable

- **WHEN** a word of a shell command contains a variable or a command substitution, or begins with
  the home-directory shorthand, and contains a path separator
- **THEN** the command is refused
- **AND** the reason states that where the path points cannot be checked
- **AND** the reason does not state that the path is outside the workspace

#### Scenario: A path joined to an option or a prefix is not let through

- **WHEN** a word joins an absolute path outside the workspace to an option or a prefix character
- **THEN** the command is refused, as the absolute path standing alone would be

#### Scenario: Either separator the platform accepts is a separator

- **WHEN** the platform accepts more than one path separator, and a relative path that the shell
  passes on with either of them resolves outside the workspace
- **THEN** the command is refused

#### Scenario: A traversal joined to an option is refused with either separator

- **WHEN** a relative path that resolves outside the workspace is joined to an option, using any
  path separator the platform accepts
- **THEN** the command is refused

#### Scenario: A backslash the shell removes is not a separator

- **WHEN** the shell that runs a command treats a backslash as an escape and removes it, and the
  path it passes on resolves inside the workspace
- **THEN** that backslash does not make the command refused

#### Scenario: A path that cannot be resolved is refused, not raised

- **WHEN** a word of a shell command cannot be resolved as a path at all
- **THEN** the call is refused with a reason
- **AND** the permission request is answered

### Requirement: A refusal's reason fits the record that carries it

The system SHALL bound the text of a refusal's reason so that the refusal can always be recorded wherever it is decided.

A refusal is recorded by the run reporting it to the Hub, and the Hub bounds the reason it accepts.
A reason that quotes a long refused word in full exceeds that bound. The report is then rejected,
and the rejection is swallowed so that reporting can never change a decision. The refusal happened
and nothing recorded it. The operator is the one participant who can widen a boundary, and cannot
do that for a refusal they never see.

Quoting part of a long word loses nothing the operator needs. What they need is that a refusal
happened, and which word it was about.

The bound is on the reason as it is sent. A word is rendered before it is quoted, and rendering can
lengthen it several times over: a character that cannot be printed is written as an escape. A
bound on the word before rendering does not bound the reason.

#### Scenario: A refusal quoting a long word is still recorded

- **WHEN** a tool call is refused over a word longer than the Hub accepts in a recorded reason
- **THEN** the reason quotes a bounded part of the word
- **AND** the refusal is recorded

#### Scenario: A word that renders longer than it is does not overflow the bound

- **WHEN** a tool call is refused over a word made of characters that are rendered as escapes
- **THEN** the reason sent is within the length the Hub accepts
- **AND** the refusal is recorded

