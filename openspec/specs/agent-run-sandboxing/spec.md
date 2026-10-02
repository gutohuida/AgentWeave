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
permission inside it. The default posture SHALL NOT widen what an agent can affect outside its own
workspace. Where the default posture is the one in which the Hub decides each tool call against the
workspace, it narrows it: a call the Hub judges to reach outside the workspace is refused.

#### Scenario: A newly created agent can edit files in its own workspace

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** that agent writes a file inside its own workspace
- **THEN** the write succeeds
- **AND** no approval was required from an operator

#### Scenario: A posture requiring an answer is not imposed by default

- **WHEN** no operator-facing approval surface exists for a provider
- **THEN** the Hub does not default that provider's runs to a posture that asks for approval

#### Scenario: The default posture never widens the workspace boundary

- **WHEN** an agent acts under the default posture
- **THEN** its ability to affect anything outside its own workspace is not widened by that posture
- **AND** where the default is the posture in which the Hub decides each tool call, a call the Hub
  judges to reach outside the workspace is refused

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

A shell may also carry a quote form that does not merely remove characters but decodes escapes into
other characters, so that a separator the command's text does not contain is present in the word
the shell produces. A path spelled that way SHALL be judged by what it decodes to, not by its text.

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

#### Scenario: A quote that spells a separator is judged by what it decodes to

- **WHEN** a shell command names a path in a quote form that the shell decodes, so that an escape
  in the quote decodes to a path separator the command's text does not contain, and the decoded
  path resolves outside the workspace
- **THEN** the command is refused
- **AND** the reason names the decoded path, not the text as typed

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

### Requirement: A word with no path separator is still judged when it names a directory by itself

Under the posture in which the Hub decides each tool call against the run's workspace, a word of a shell command that contains no path separator but names the parent directory, or is the home-directory shorthand in a form the shell substitutes, or carries either as an option's value within the same word, SHALL be judged rather than exempted as not a path.

A word with no path separator usually names an entry of the directory the shell runs in, so it
cannot leave the workspace, and judging every such word would cost a resolution per word for no
gain. Two spellings are exceptions, because each names a directory entirely by itself. The parent
directory, `..`, is the directory above. The home-directory shorthand, alone, followed by a sign,
or followed by a user name, is a home or remembered directory that the shell substitutes when it
runs. A boundary that refuses `../` and allows `..` has not drawn a boundary, since the two name the
same directory.

A word that names the parent directory SHALL be judged by where it resolves against the workspace,
exactly as the same word followed by a separator is judged. Where it resolves outside the
workspace, the refusal SHALL say so and name the word.

A word that is the home-directory shorthand alone, followed by a sign, or followed by a user name
SHALL be refused with a reason saying where it points cannot be checked, as a word that begins with
the shorthand and contains a separator already is. It SHALL NOT be refused with a reason claiming it
is outside the workspace. The shorthand followed by a number names an entry of the shell's
directory stack, which holds only directories a command named as it pushed them. The shorthand
followed by characters that begin with a digit, or that no user name contains, such as an
approximate figure in a commit message, is passed on unchanged. Neither is one of these forms.

An option can carry its value in its own word, with no separator between them: a short option with
its value glued on, or an option joined to its value by a colon, which one dialect uses for its own
parameters and some programs accept for theirs. A value carried that way that names the parent
directory SHALL be judged as the parent directory, and the refusal SHALL name the whole word.
Where the dialect's shell resolves the home-directory shorthand in such a value, a value that is the
shorthand in one of the forms above SHALL be refused as uncheckable. This is what the requirement that a word joining a path to an option be judged at
least as strictly as the path alone asks of these spellings.

The word judged is the argument the shell passes on. An argument ends at a NUL character, so a word
the shell decodes into the parent directory followed by a NUL and more characters SHALL be judged
as the parent directory.

An ordinary word with no path separator, such as a file name in the directory the shell runs in, an
option, the current directory, a name made of three or more dots, a revision, the shorthand before
a number or a figure, or the shorthand carried by an option where the dialect's shell does not
resolve it, SHALL still be allowed. This requirement does not claim that every other separator-less word stays inside the
workspace: a word that becomes another directory only when the shell expands a variable or a brace
pattern in it is outside its scope.

#### Scenario: The parent directory alone is refused

- **WHEN** a shell command, in either dialect, names the parent directory as a word of its own and
  that directory is outside the workspace
- **THEN** the command is refused
- **AND** the reason states that the word is outside the workspace and names it

#### Scenario: The parent directory and the parent directory followed by a separator are judged alike

- **WHEN** one shell command names the parent directory alone and another names it followed by a
  path separator, otherwise identical
- **THEN** both commands receive the same decision
- **AND** this holds both when the workspace's parent is outside it and when the workspace is a
  filesystem root, whose parent is itself

#### Scenario: The parent directory assembled from quotes is refused

- **WHEN** a shell command writes the parent directory from pieces the shell joins by removing
  quotes between them, and that directory is outside the workspace
- **THEN** the command is refused

#### Scenario: The parent directory as an option's value is refused

- **WHEN** a shell command, in either dialect, passes the parent directory as the value of an
  option, joined to the option's name by an equals sign or a colon, or glued to a short option or a
  run of short options with nothing between them, and that directory is outside the workspace
- **THEN** the command is refused
- **AND** the reason names the whole word, as the shell passes it on

#### Scenario: The parent directory ended by a NUL is refused

- **WHEN** a shell command names a quote form that decodes to the parent directory followed by a
  NUL character and further characters, and that directory is outside the workspace
- **THEN** the command is refused

#### Scenario: The home-directory shorthand alone is refused as uncheckable

- **WHEN** a shell command, in either dialect, names a word with no path separator that is the
  home-directory shorthand alone, followed by a sign, or followed by a user name
- **THEN** the command is refused
- **AND** the reason states that where the word points cannot be checked
- **AND** the reason does not state that the word is outside the workspace

#### Scenario: The home-directory shorthand as a parameter's value is refused as uncheckable

- **WHEN** a PowerShell command passes the home-directory shorthand alone as the value of a
  parameter, joined to the parameter's name by a colon, with no path separator in the word
- **THEN** the command is refused
- **AND** the reason states that where the word points cannot be checked

#### Scenario: An ordinary name with no separator still stands

- **WHEN** a shell command names only words with no path separator that are neither the parent
  directory nor begin with the home-directory shorthand, and carry neither as an option's value,
  including the current directory, a name made of three or more dots, a name containing two dots
  between other characters, a short option, and a revision that contains the shorthand after its
  first character
- **THEN** the command is allowed

#### Scenario: The home-directory shorthand before a figure stands

- **WHEN** a shell command names a word with no path separator that begins with the home-directory
  shorthand followed by a number, with or without a sign, or by characters that begin with a digit
  or that no user name contains, such as an approximate figure in a commit message
- **THEN** that word does not make the command refused

#### Scenario: The home-directory shorthand joined to an option stands where the shell leaves it

- **WHEN** a bash command passes the home-directory shorthand glued to a short option, or joined to
  an option's name by a colon, with no path separator in the word
- **THEN** that word does not make the command refused

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

### Requirement: A Copilot run's posture is decided by the Hub over ACP

The Hub SHALL answer every permission request a Copilot run raises over the Agent Client Protocol, deciding it by the run's permission posture with the same shell and path judge the workspace posture uses for Claude, and SHALL NOT make that answer depend on the Hub's MCP server.

The Hub decides only what Copilot asks it. Copilot runs the shell commands it classes as read-only
without raising any request, so the Hub never sees or judges those; that is a difference from a
Claude run, whose every shell command is judged. The Hub SHALL NOT claim to judge what Copilot did
not ask about.

The Hub SHALL answer as follows:

- **Workspace only**, which is also how a run that states no posture is decided. A shell command
  Copilot asks about SHALL be judged in the dialect of the shell Copilot reports running it. A
  command whose shell is not known SHALL be judged in every dialect the Hub reads, and refused if any
  refuses. A shell request that carries no command text SHALL be refused. A file change and an
  out-of-directory read SHALL be judged against the run's workspace, path by path, and one that names
  no path SHALL be refused. A web address request SHALL be allowed only when Copilot reports it as
  coming from its own fetch tool and it does not ask to bypass Copilot's sandbox; any other web
  address request SHALL be judged as the text of a shell command is, so only the run's own Hub
  passes. A call to the Hub's own `agentweave` tools SHALL be allowed. A call SHALL count as the
  Hub's own only when Copilot's own report of the call names the Hub's server and a tool the Hub's
  server serves, and Copilot reported that server as loaded from the Hub's own configuration and
  from no workspace or plugin source. Text the model writes, such as a tool call's title, SHALL NOT
  decide which server a call belongs to. A tool call whose server Copilot did not report SHALL be
  refused before any rule about a particular server applies, as SHALL a request kind the Hub does
  not recognise.
- **Ask me.** Every request except the Hub's own tools SHALL be put to the operator as a card while
  the request is held open. A card for a tool call whose server Copilot did not report SHALL say so,
  and SHALL NOT name the server from text the model wrote. It SHALL be refused when the operator's
  wait runs out.
- **Full access.** The run SHALL be put into Copilot's allow-all mode, except on a specification
  turn, which is decided as described below. When Copilot refuses that
  mode, the run SHALL fall back to deciding against its workspace, and SHALL say so in its timeline,
  quoting the reason Copilot gave. It SHALL NOT approve through the Hub what Copilot withheld.
- **Edit files.** A file change inside the workspace SHALL be allowed. Any other request except the
  Hub's own tools SHALL be refused.

Under every posture except Full access, and on a specification turn under every posture, the Hub
SHALL set Copilot's session mode on every turn, including a resumed one, and SHALL confirm before
sending the prompt that Copilot's allow-all mode is off. A turn whose allow-all mode cannot be turned off SHALL NOT be prompted, and SHALL fail with the
reason. A runner option that widens what Copilot approves by itself SHALL NOT reach a run under any
posture except Full access.

The Hub SHALL answer every request exactly once, and SHALL NOT grant an approval for the rest of a
session in place of the request in front of it. A refusal the Hub decided without the operator
SHALL be recorded as other runtime refusals are. Deciding one request SHALL NOT stall the Hub's
handling of other runs, however long resolving a path takes.

A turn triggered with a specification document open SHALL have Copilot's file-editing tools
removed, except its file-creation tool, whatever the posture. The Hub SHALL refuse every file
change such a turn asks for, in every posture, except a write the Hub itself recognises as the
run's own call to the Hub, and SHALL NOT put such a turn into Copilot's allow-all mode, so that
every file change reaches the Hub. Under Full access, every other request such a turn raises SHALL
be decided as under Workspace only, and the Hub SHALL NOT allow it on Full access's account: a turn
that never asks Copilot for allow-all cannot learn whether Copilot, or an organisation's policy,
would have withheld it. Under Full access a specification turn therefore behaves as Workspace only.
It SHALL NOT run in Copilot's plan mode until a drive has shown
that plan mode leaves the turn's specification duties intact and cannot leave the turn waiting on
a request nobody can answer.

#### Scenario: A command outside the workspace is refused under Workspace only

- **WHEN** a Copilot run under Workspace only asks to run a PowerShell command that writes to a path outside its workspace
- **THEN** the Hub answers the request with a refusal
- **AND** the refusal is recorded as a runtime refusal in the run's timeline

#### Scenario: A file change inside the workspace is allowed under Workspace only

- **WHEN** a Copilot run under Workspace only asks to edit a file inside its workspace
- **THEN** the Hub answers the request with a one-time allow

#### Scenario: The Hub's own tool is allowed under Ask me

- **WHEN** a Copilot run under Ask me asks to call the `agentweave` server's `send_message`
- **THEN** the Hub allows it without opening an operator card

#### Scenario: A command is put to the operator under Ask me

- **WHEN** a Copilot run under Ask me asks to run a shell command
- **THEN** an operator card opens and the request stays unanswered until the operator decides or the wait runs out
- **AND** a wait that runs out is answered with a refusal

#### Scenario: Full access withdrawn by Copilot

- **WHEN** a Copilot run is started under Full access and Copilot does not offer its allow-all option, or refuses to turn it on
- **THEN** the run decides each request against its workspace
- **AND** its timeline says that Full access was not granted, quoting the reason Copilot gave

#### Scenario: A read-only command Copilot does not ask about

- **WHEN** a Copilot run under Workspace only runs a shell command that Copilot classes as read-only
- **THEN** Copilot raises no permission request and the Hub makes no decision about it
- **AND** nothing the Hub records claims that the command was judged

#### Scenario: A web address raised by a shell command

- **WHEN** a Copilot run under Workspace only raises a web address request for `https://example.com` that Copilot reports as belonging to a shell command
- **THEN** the Hub answers the request with a refusal

#### Scenario: A web address from Copilot's fetch tool

- **WHEN** a Copilot run under Workspace only raises a web address request that Copilot reports as belonging to its fetch tool, without asking to bypass its sandbox
- **THEN** the Hub answers the request with a one-time allow

#### Scenario: A request to bypass Copilot's sandbox

- **WHEN** a Copilot run under Workspace only raises a web address request that asks to bypass Copilot's sandbox
- **THEN** the Hub answers the request with a refusal

#### Scenario: A resumed session left in plan mode

- **WHEN** a Copilot conversation's earlier turn left its session in plan mode and the next turn is not a specification turn
- **THEN** the Hub sets the session back to its ordinary mode before sending the prompt

#### Scenario: A resumed session that loads with allow-all on

- **WHEN** a Copilot run under Workspace only loads a session whose allow-all mode is on
- **THEN** the Hub turns allow-all off before sending the prompt
- **AND** if allow-all stays on, the turn fails with the reason and no prompt is sent

#### Scenario: A runner option that widens approvals

- **WHEN** a Copilot runner's options include `--yolo` or `--allow-tool` and a run is started under Workspace only
- **THEN** the spawned command does not carry that option
- **AND** the run's timeline names the option that was removed

#### Scenario: A path that names a network share

- **WHEN** a Copilot run asks to edit a path on a network share that takes many seconds to resolve
- **THEN** other runs and the Hub's routes keep being served while that request is decided

#### Scenario: A run with no posture chosen

- **WHEN** a Copilot run whose conversation and agent state no permission posture asks to run a command that writes outside its workspace
- **THEN** the Hub answers the request with a refusal, as under Workspace only

#### Scenario: A foreign server named like the Hub's

- **WHEN** a Copilot run asks to call a tool of an MCP server named `agentweave-x` or `agentweave__x`
- **THEN** the Hub judges the call as a foreign server's rather than allowing it as its own

#### Scenario: The Hub's server name with a tool the Hub does not serve

- **WHEN** a Copilot run under Workspace only asks to call a tool the Hub's server does not serve, on a server Copilot reports as `agentweave`, with a command argument that writes outside the workspace
- **THEN** the Hub judges the call as a foreign server's and answers it with a refusal

#### Scenario: A repository claims the Hub's server name

- **WHEN** Copilot reports that the server named `agentweave` was loaded from the workspace or from a plugin
- **THEN** no call to that server is allowed as the Hub's own
- **AND** the run's timeline says why

#### Scenario: A tool call whose title imitates the Hub's tool

- **WHEN** a Copilot run under Ask me asks to call a tool whose displayed title reads `agentweave-send_message`, and Copilot's own report of the call names another server or no server
- **THEN** the Hub does not allow it as its own tool

#### Scenario: A tool call whose server Copilot did not report

- **WHEN** a Copilot run under Workspace only raises a permission request for a tool call that Copilot has not reported as belonging to any MCP server
- **THEN** the Hub answers the request with a refusal that says the server was not reported

#### Scenario: A shell request with no command text

- **WHEN** a Copilot run under Workspace only raises a shell permission request that carries no command text
- **THEN** the Hub answers the request with a refusal

#### Scenario: An unknown request kind

- **WHEN** a Copilot run raises a permission request of a kind the Hub does not recognise
- **THEN** the Hub answers it with a refusal rather than leaving it unanswered

#### Scenario: A specification turn has no write tools

- **WHEN** a Copilot turn is triggered with a specification document open under Full access
- **THEN** the spawned command removes Copilot's file-editing tools other than its file-creation tool
- **AND** the session's allow-all mode is off before the prompt is sent
- **AND** a request to create a file in the workspace is refused and recorded as a runtime refusal
- **AND** the session is not put into plan mode while no drive has shown plan mode to be safe for specification turns

#### Scenario: A specification turn under Full access is decided as Workspace only

- **WHEN** a Copilot turn is triggered with a specification document open under Full access
- **AND** it asks to run a PowerShell command that writes to a path outside its workspace
- **THEN** the Hub refuses the request, as it would under Workspace only, and records the refusal
- **AND** a shell command that stays inside the workspace is allowed, as it would be under Workspace only

#### Scenario: Approvals do not depend on MCP

- **WHEN** a Copilot run's `agentweave` MCP server fails to start
- **THEN** the run's permission requests are still answered by the Hub under the run's posture

### Requirement: A Copilot run receives no GitHub token or permission override it was not given

The Hub SHALL remove `GH_TOKEN`, `GITHUB_TOKEN` and `COPILOT_GITHUB_TOKEN` from every Copilot process's environment unless the agent's own configured environment names them, and SHALL remove Copilot's allow-all and folder-trust variables from it always.

A token in the environment silently replaces the operator's Copilot sign-in. A token the Hub
happened to inherit would therefore change whose plan and whose policy a run is billed and governed
by.

`COPILOT_ALLOW_ALL` approves every tool without asking and, set to `true`, also trusts the working
folder, which loads the repository's own hooks, plugins and MCP servers. The Hub SHALL remove it,
and the other variables Copilot reads to widen approvals or trust a folder, from every Copilot
process it starts, whether the Hub inherited them or the agent's configuration names them. When the
agent's configuration names one, the run's timeline SHALL say it was removed and that the Full
access posture is the way to grant it. The Copilot home a run uses SHALL be the one the Hub chose
for it, whatever the environment names.

Copilot also reads its model provider, its model and an offline switch from the environment. A
provider variable the Hub happened to inherit would silently send a subscription run to another
provider. The Hub SHALL remove every provider variable, the model variable and the offline variable
from every Copilot process it starts for a runner that has no provider configured, whether the Hub
inherited them or the agent's configuration names them, and when the agent's configuration names
one, the run's timeline SHALL say it was removed.

#### Scenario: An ambient token is not passed on

- **WHEN** the Hub process has `GH_TOKEN` set and a Copilot agent's configuration does not name it
- **THEN** the spawned Copilot process's environment has no `GH_TOKEN`

#### Scenario: An agent that names a token keeps it

- **WHEN** a Copilot agent's configured environment names `COPILOT_GITHUB_TOKEN`
- **THEN** the spawned Copilot process receives that variable as the agent configured it

#### Scenario: An ambient allow-all variable is not passed on

- **WHEN** the Hub process has `COPILOT_ALLOW_ALL=true` set and a Copilot run is started under Workspace only
- **THEN** the spawned Copilot process's environment has no `COPILOT_ALLOW_ALL`
- **AND** the run's permission requests are still decided by the Hub

#### Scenario: An ambient provider variable is not passed on

- **WHEN** the Hub process has `COPILOT_PROVIDER_BASE_URL` and `COPILOT_MODEL` set and a Copilot run is started on a runner with no provider configured
- **THEN** the spawned Copilot process's environment has neither variable, nor any other variable whose name begins `COPILOT_PROVIDER_`

#### Scenario: An agent that names the allow-all variable

- **WHEN** a Copilot agent's configured environment names `COPILOT_ALLOW_ALL`
- **THEN** the spawned Copilot process's environment has no `COPILOT_ALLOW_ALL`
- **AND** the run's timeline says it was removed and names the Full access posture

### Requirement: The built-in posture a run receives is the posture shown for it

The built-in posture a run receives when neither its conversation nor its agent states one SHALL be decided in one place per provider, and every surface that shows a posture at rest SHALL show that posture.

For a run the Hub can answer, that posture is the one in which the Hub decides each tool call
against the run's workspace. A posture that accepts edits but leaves execution to a prompt nobody
can answer lets an agent write code and never run it. A run the Hub cannot answer receives the
posture that accepts edits, and a provider whose own default already confines the run to its
workspace keeps that default.

Flags that serve the enforced posture SHALL be emitted only for that posture, and only where the
mechanism answering them is present.

#### Scenario: The default spawned is the default shown

- **WHEN** a non-yolo run is spawned with no posture selected by its conversation or its agent
- **THEN** it is spawned under the built-in posture for its provider
- **AND** that is the posture the app showed for it at rest

#### Scenario: Other postures carry no enforcement machinery

- **WHEN** a run selects a posture other than the enforced one
- **THEN** its command carries nothing referring to the enforcement mechanism

#### Scenario: No enforcement is claimed without an answerer

- **WHEN** the enforced posture is selected but no mechanism is present to answer its requests
- **THEN** the command does not claim enforcement it cannot perform

### Requirement: An operator asked to decide a call is shown what the workspace posture would decide

Under the posture in which the operator answers each tool call, the request the operator is shown SHALL carry the decision the posture that checks each call against the run's workspace would have reached for the same call, with its reason, and that decision SHALL be presented as advice and SHALL NOT answer the request.

The operator is the last participant who can stop the call, and decides in seconds under a
timeout. The Hub already computes, for the same run, the boundary this posture would enforce. A
request that withholds it asks for a judgement without its most important input, and makes the
posture in which a human decides the one in which the boundary is least visible.

The decision SHALL be reached by the same check that answers under the workspace posture for that
run's provider, so that the advice and the enforced answer cannot disagree. Where no such decision
was reached, the request SHALL say nothing about the boundary rather than guess.

An allowed decision for a shell command SHALL NOT be presented as a statement that the command stays
inside the workspace. A command's text can name values the shell decides when it runs, and the check
reads text.

Carrying the decision SHALL NOT make asking the operator fail. A Hub that does not accept it SHALL
still be asked.

#### Scenario: A call outside the workspace is marked on the request

- **WHEN** a run under the operator-answered posture asks to write a path outside its workspace
- **THEN** the request shown to the operator states that the workspace posture would refuse it
- **AND** states the reason
- **AND** the operator can still allow it

#### Scenario: A call inside the workspace is marked as allowed, without a containment claim

- **WHEN** a run under the operator-answered posture asks to run a shell command the workspace
  posture would allow
- **THEN** the request states that the workspace posture would allow it
- **AND** does not state that the command stays inside the workspace

#### Scenario: A decision checked by working directory only says so

- **WHEN** the provider's workspace check for a command reads only the working directory it would
  run in, not the command
- **THEN** the request's stated reason says the call was checked by working directory only
- **AND** does not say the command was read

#### Scenario: No decision, no claim

- **WHEN** a request was opened without a workspace decision
- **THEN** the request states nothing about the workspace boundary

#### Scenario: An older Hub is still asked

- **WHEN** the Hub refuses a request because it carries the workspace decision
- **THEN** the request is opened without it
- **AND** the operator is still asked

### Requirement: The Hub's own call command is decided like the Hub's own tools

Wherever the Hub answers a Claude or Copilot run's permission request, it SHALL allow, in every posture and without asking the operator, a request of the harness's shell tool whose command is exactly one invocation of the call command and a file write that names at least one path and only arguments files inside the run's own calls directory, and SHALL decide every other request exactly as it would without this rule.

The plane's operations were never subject to the run's posture: the tool-protocol tools are allowed
by standing, because asking a person to approve each message would make collaboration unusable and
each call is already bounded by the run's own credential. The call command reaches the same
operations under the same credential, and nothing else, so it has the same standing. Its arguments
must be written to a file first, and that write is part of the same call.

"Exactly one invocation" is read from the command's text in the shell it will run in: the command
name `aw-tool` by itself (not a path to it), then an operation the command can perform, then at most
one arguments file given as a plain relative path to a `.json` file inside the run's calls directory
within its workspace, not beginning with a hyphen, and nothing else. The command's text may hold only
the ASCII characters such an invocation needs: letters, digits, the dot, the underscore, the hyphen,
the forward slash, the space, and in PowerShell the backslash. Any other character anywhere in the command means it is not one
invocation, whatever that character would do. The rule does not list the shell syntax it refuses,
because a list of refused syntax fails open at the first form it forgot, and one was found while this
requirement was reviewed: a parenthesised path, which PowerShell runs as a command. The calls
directory is the Hub's own, and the repository ignores it.

The calls directory must be itself. It is the directory of that name inside the run's workspace, taken
as named and not by following links. When it, or the directory that holds it, is a link or junction to
somewhere else, no path is inside it, and no call or write gains standing from this rule. Otherwise a
link made once, under a posture that allowed it, would turn every later write "inside the calls
directory" into a write to wherever the link points, under every posture, including one that asks
about every other write. The Hub makes the directory a real directory at the start of each turn,
removing a link found in its place without touching what the link pointed to. The call command applies
the same rule to the file it reads, so a harness rule that allows the command by its name alone still
reads only an arguments file inside the calls directory.

Only the harness's own shell tools are read this way. A request of any other tool is not a shell
command merely because its input has a field of that name: what a foreign tool does with its other
fields cannot be seen, so sparing it the operator's question would widen what the run may do
unasked. A shell request whose tool the Hub cannot name is not one of the harness's shell tools
either, and gets no standing from this rule.

The call command runs its interpreter ignoring the interpreter's own environment variables, user
site and site customisation, so that an interpreter setting made earlier in the same shell cannot
change what the allowed invocation runs. That is all it isolates. The shell that resolves the
command's name is not isolated: in a shell session that persists between a run's commands, an earlier
command can define a function or alias of the same name, import a module that does, put another
directory ahead on the search path (as activating a virtual environment does), or change the program
Windows uses to run command scripts, and the same text then runs something else. A machine's
command-processor start-up setting also runs before every call. This rule cannot see that, and it
does not claim to; the earlier command was itself decided under the run's posture. Under the posture
that asks the operator, this means the operator's approval of one such earlier command also decides
what later calls in that session run without asking. That residual is accepted and stated, not
closed.
Deciding this rule never fails: a request it cannot judge is one it does not match.

A Codex run's command approvals are not read this way. Codex hands the Hub the command as its
harness wrapped it for the shell, not as the model wrote it, and they are decided as they were before
this rule.

A request that is almost an invocation is not refused by this rule. It is decided exactly as it would
be without it, so this rule can only spare a request from being asked about, never refuse one or
allow one the workspace decision would refuse for any other reason.

#### Scenario: A plain call is allowed without asking

- **WHEN** a run under the posture that asks the operator runs `aw-tool create_task
  .agentweave/calls/1.json`, in bash or in PowerShell
- **THEN** the call is allowed without the operator being asked
- **AND** the decision is reported like any other decision

#### Scenario: Writing the arguments file is allowed without asking

- **WHEN** a run under the posture that asks the operator writes `.agentweave/calls/1.json` in its own
  workspace
- **THEN** the write is allowed without the operator being asked

#### Scenario: A second command in the same text is not a plain call

- **WHEN** a run's shell command is `aw-tool create_task .agentweave/calls/1.json; rm x`, or pipes,
  redirects, or substitutes anything
- **THEN** the request is decided as it would be without this rule

#### Scenario: A grouped or quoted word is not a plain call

- **WHEN** a run's PowerShell command is `aw-tool list_tasks (.agentweave/calls/1.json)`, or wraps
  any word in braces, quotes, or joins words with a comma
- **THEN** the request is decided as it would be without this rule

#### Scenario: An arguments file elsewhere is not a plain call

- **WHEN** the arguments file named is outside the run's calls directory, reaches it through `..`, is
  absolute, or is not a `.json` file
- **THEN** the request is decided as it would be without this rule

#### Scenario: Another tool's command field is not a shell command

- **WHEN** a run under the posture that asks the operator requests a tool other than its shell tool
  whose input holds a field named `command` with the text of a plain call
- **THEN** the request is decided as it would be without this rule

#### Scenario: A file write that names no path is not allowed by it

- **WHEN** a write request names no path at all
- **THEN** the request is decided as it would be without this rule

#### Scenario: A path to the command is not the command

- **WHEN** a run names the command by a path, such as `./aw-tool` or a full path
- **THEN** the request is decided as it would be without this rule

#### Scenario: A write that only resolves into the calls directory through a link is not allowed by it

- **WHEN** a written path resolves, after links are followed, outside the run's calls directory
- **THEN** the write is decided as it would be without this rule

#### Scenario: A calls directory that is itself a link is not the calls directory

- **WHEN** the run's calls directory, or the directory that holds it, is a link or junction to another
  directory, and a run under the posture that asks the operator writes a JSON file through it or names
  one in a call
- **THEN** the request is decided as it would be without this rule
- **AND** the call command, given that file, reads nothing and reports a usage error

#### Scenario: A shell request from an unnamed shell tool is not a plain call

- **WHEN** a run under the posture that asks the operator makes a shell request whose tool the Hub
  cannot name, with the text of a plain call
- **THEN** the request is decided as it would be without this rule

### Requirement: A Claude run pre-allows the Hub's call command

Every non-yolo Claude run the Hub spawns SHALL allow the call command by standing in the harness's own tool allowlist, in both its shell tools, whether or not the Hub's tool-protocol server is configured.

A Claude run whose approver is not there cannot be asked about anything, so a request that needs
approval is denied. On the path without the Hub's server, that is every shell command, and a
plane reachable only through a shell command is unreachable (F301). Allowing the call command by
standing makes the plane reachable there without making anything else reachable. The harness's rule
names the command, not its arguments, so the command itself reads only an arguments file inside the
run's calls directory, and a file named anywhere else is a usage error with no request made.

#### Scenario: The allowlist names the call command

- **WHEN** the Hub spawns a non-yolo Claude run, with or without its own tool-protocol server
- **THEN** the command line allows the call command in the harness's bash tool and its PowerShell tool

#### Scenario: Nothing else is allowed by it

- **WHEN** such a run runs a shell command that is not the call command
- **THEN** it is decided as it would be without this allowlist entry

