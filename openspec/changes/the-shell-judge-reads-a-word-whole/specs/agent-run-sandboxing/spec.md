## MODIFIED Requirements

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
be judged at least as strictly as the path within it would be if it stood alone. A path can begin
inside a word only where something other than a path name ends: after a character the shell or an
inner shell treats as a boundary, after a quote, after a character that glues a path to a host,
a revision or a field name, or after a leading short option. A separator that continues a name is
not the start of a path, and the part of a relative word after such a separator SHALL NOT be judged
as a path of its own. Each piece read this way SHALL be judged as the path it spells, resolved
against the workspace, and so SHALL the word with the quotes an inner shell would remove taken out.

A glob pattern in a path is judged as the names it can match. A component that can match the parent
directory SHALL be judged as the parent directory.

In the dialect whose shell provides them, the null device and the standard streams are not
filesystem destinations, and naming them SHALL NOT refuse a command. No other device path is
exempted.

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

#### Scenario: A pattern or a name with a separator in it is judged whole

- **WHEN** a shell command names a relative word inside the workspace that contains a separator and
  also a glob character, a package scope, a revision prefix, a format directive or a regular
  expression
- **THEN** that word does not make the command refused

#### Scenario: A traversal inside a non-plain word is still refused

- **WHEN** a word that is not a plain path contains a piece that resolves outside the workspace,
  whether glued to an option, a prefix character or a host, or joined by quotes an inner shell
  removes
- **THEN** the command is refused
- **AND** the reason names that piece, not the tail of a name

#### Scenario: A glob that can match the parent directory is refused

- **WHEN** a path component is a pattern beginning with a dot that can match the parent directory,
  and the path it forms that way resolves outside the workspace
- **THEN** the command is refused

#### Scenario: The null device may be named

- **WHEN** a bash command redirects to or names the null device or a standard stream
- **THEN** that word does not make the command refused
- **AND** a PowerShell command naming the same path is still judged as a path

## ADDED Requirements

### Requirement: A brace pattern is judged as the words it expands to

Under the posture in which the Hub decides each tool call against the run's workspace, a bash command's brace pattern SHALL be judged as every word the shell expands it to, and a pattern that expands to more words than can be judged SHALL be refused as uncheckable.

A shell that expands brace patterns hands each alternative on as a word of its own, before any
other expansion. A pattern whose alternatives include the parent directory names the parent
directory, however harmless its text looks, and a pattern whose alternatives are all inside the
workspace names nothing outside it. Judging the text instead of the alternatives errs both ways:
it lets `.{,.}` through, and it refuses `src/{a,b}`.

A brace the shell does not expand, because it is quoted, escaped, opens a parameter expansion, or
holds no alternatives, SHALL be read as the literal character it is. Because a quoted word may be
handed to an inner shell that does expand it, a brace pattern left literal by the outer shell, in
either dialect, SHALL also be judged as the words that inner shell would expand it to, and a
refusal of either reading refuses the command.

#### Scenario: A brace pattern that expands to the parent directory is refused

- **WHEN** a bash command names a brace pattern one of whose alternatives resolves outside the
  workspace
- **THEN** the command is refused
- **AND** the reason names that alternative

#### Scenario: A brace pattern whose alternatives are inside stands

- **WHEN** a bash command names a brace pattern all of whose alternatives resolve inside the
  workspace
- **THEN** that pattern does not make the command refused

#### Scenario: A quoted brace is also judged as an inner shell expands it

- **WHEN** a command hands an inner shell a quoted brace pattern one of whose alternatives resolves
  outside the workspace
- **THEN** the command is refused

#### Scenario: A quoted brace whose alternatives are harmless stands

- **WHEN** a command names a quoted brace pattern, such as an awk program or an inline JSON value,
  none of whose alternatives resolves outside the workspace
- **THEN** that pattern does not make the command refused

#### Scenario: A pattern too large to judge is refused as uncheckable

- **WHEN** a bash command names a brace pattern that expands to more words than the judge examines
- **THEN** the command is refused
- **AND** the permission request is answered

### Requirement: A remote address written without a scheme is decided as a network address

Under the posture in which the Hub decides each tool call against the run's workspace, a shell word written as a user at a host followed by a colon, or as a host followed by a colon, a port and a path, SHALL be refused as a network address and SHALL NOT be judged as a path.

These two forms are what a program reads as a remote location: the first is how a copy over a
secure shell and a repository clone name their source, the second is a host and port. Read as
paths they are relative words inside the workspace, and a judge that reads words whole would allow
them for a false reason, as the earlier reading refused them for one.

A host and port with nothing after them, and any other word with a colon, are not covered by this
requirement.

#### Scenario: A user-at-host remote is a network address

- **WHEN** a shell command names a word written as a user at a host followed by a colon
- **THEN** the command is refused
- **AND** the reason states that the word is a network address

#### Scenario: A host and port with a path is a network address

- **WHEN** a shell command names a word written as a host, a colon, a port and a path
- **THEN** the command is refused
- **AND** the reason states that the word is a network address
