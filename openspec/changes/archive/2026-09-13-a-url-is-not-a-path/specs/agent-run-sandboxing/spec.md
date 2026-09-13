## ADDED Requirements

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
