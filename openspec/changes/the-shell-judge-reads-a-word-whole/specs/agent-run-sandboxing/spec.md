## MODIFIED Requirements

### Requirement: A posture exists in which the workspace boundary is enforced per tool call

The Hub SHALL offer a permission posture under which each of a run's tool calls is decided against
the run's own workspace, rather than permitted in advance.

Under that posture a tool call confined to the run's workspace is allowed, and one reaching outside
it is refused with a reason stating what was refused and why. The comparison SHALL be made on fully
resolved paths, so that a relative traversal or a symbolic link cannot escape a boundary that an
unresolved comparison would have accepted. A traversal that follows a link is resolved by some
programs from where the link points and by others from the text as written, so such a path SHALL be
judged both ways, and it is inside only when both readings are inside.

For a shell command, the paths compared are the ones its text names as the shell that runs it will
read them (see *A path in a shell command is judged by where it resolves*). A glob pattern among
them SHALL be judged by the entries it matches in the filesystem as well as by its text, so that a
link it matches cannot carry the command outside, and a pattern that would need more entries
examined than the check allows SHALL be refused. A word with no path separator is not one of these
paths: *A word with no path separator is still judged when it names a directory by itself* says
which such words are judged. A path the command computes only when it runs is not one its text
names, and this requirement does not claim that such a path is judged.

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

#### Scenario: A traversal after a link is judged from where the link points

- **WHEN** a path names a link inside the workspace followed by a parent-directory step, and the
  link points to a directory from which that step leaves the workspace, although the path read as
  text stays inside
- **THEN** it is refused
- **AND** a link to a directory at the same depth, whose parent is inside, does not make it refused

#### Scenario: A glob that matches a link out of the workspace is refused

- **WHEN** a shell command names a glob pattern that the shell would expand to an entry of the
  workspace that is a link resolving outside it, although the pattern's text names nothing outside
- **THEN** the command is refused
- **AND** the reason names where the matched entry resolves

#### Scenario: A glob too large to examine is refused

- **WHEN** a shell command names a glob pattern whose matching needs more directory entries examined
  than the check allows
- **THEN** the command is refused as uncheckable
- **AND** the permission request is answered

#### Scenario: An unestablished boundary refuses

- **WHEN** the run's workspace cannot be determined
- **THEN** actions under this posture are refused

#### Scenario: Collaboration is not a filesystem decision

- **WHEN** a run under this posture uses the Hub's own tools
- **THEN** those calls are allowed

---

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

A network address need not carry a scheme. A word written as a user at a host followed by a colon,
where the host is a domain name, an IP address or `localhost`, and a word written as a host, a
colon, a port and a path, SHALL be decided as network addresses, whether or not the word also holds
a path separator or an expansion. Any other word that contains a colon and no scheme, such as a
name, a colon and a relative path, or a name at a single-word alias and a colon, SHALL be judged as
the paths it spells: the same text names a revision and a path, or a package and its version, and
this posture cannot tell a host from either. A copy to a remote host written that way is therefore
not refused by this requirement, and allowing it SHALL NOT be read as a statement that the command
names no network address.

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

#### Scenario: A user at a host is a network address without a scheme

- **WHEN** a shell command names a word written as a user at a host whose name is a domain name, an
  IP address or `localhost`, followed by a colon, with or without a path separator after it
- **THEN** the command is refused
- **AND** the reason states that the word is a network address

#### Scenario: A host and port with a path is a network address without a scheme

- **WHEN** a shell command names a word written as a host, a colon, a port and a path
- **THEN** the command is refused
- **AND** the reason states that the word is a network address

#### Scenario: A name, a colon and a relative path is read as a path

- **WHEN** a shell command names a word written as a name, a colon and a relative path, with no
  user and no port, such as a revision and a file or a remote copy's relative destination
- **THEN** the word is judged as the paths it spells, not as a network address

#### Scenario: A package or image reference is not a network address

- **WHEN** a shell command names a word written as a name at a single-word qualifier followed by a
  colon, such as an image digest or a package-manager protocol
- **THEN** the word is not refused as a network address

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
The word's value as a whole SHALL also be judged as the path it spells, with and without those
quotes, because a character that divides it into pieces is also a name character to the shell; on
a platform whose file names cannot hold a colon, the value is judged whole between its colons.
Because an inner shell also removes a backslash before any character, and a shell between the
command and that one may remove a level first, every word holding a backslash SHALL also be judged
with one level of those escapes removed, and again with each further level removed until a level
removes nothing, each as a word in its own right, whether or not it reads as a plain path.
On a platform with drive letters, a letter and a colon that begin a word or a piece name that drive
in every dialect, because a program the shell starts reads them so; that colon SHALL NOT divide
them. A piece that begins with the home-directory shorthand, or a drive whose path begins with it,
SHALL be refused as uncheckable, because a shell expands the shorthand after a colon in an
assignment-shaped word. A word holding a provider qualifier (`Provider::path`) SHALL NOT be read as
a plain relative path; the path after the qualifier is judged.

A glob pattern in a path is judged as the names it can match. A component that can match the parent
directory SHALL be judged as the parent directory, and so SHALL a component holding an extended
pattern group one of whose alternatives begins with a dot. The characters inside such a group SHALL
NOT divide the word. A glob SHALL also be judged by the entries it matches in the filesystem, so that
a match that is a link is judged by where the link resolves, and this holds for a pattern an inner
shell would expand as much as for one the outer shell expands. A bracket expression that opens or
closes a word is part of its pattern, so a word SHALL also be judged with the brackets at its edges
kept, and a component that opens with a bracket expression able to match a dot SHALL be read as
beginning with a dot. A parent-directory step after a link a glob matched SHALL be judged from where
that link points.

In the dialect whose shell provides them, the null device and the standard streams are not
filesystem destinations, and naming them SHALL NOT refuse a command. On a platform with drive
letters only that shell maps them, so there this holds only for a whole word or a redirect target,
and a script's own text naming them is judged as a path. No other device path is exempted.

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

#### Scenario: A link behind a character that divides a word is judged by where it resolves

- **WHEN** a relative word of a shell command passes through a link that resolves outside the
  workspace, and the link, or a directory before it, is named with a character that divides the
  word into pieces, such as a package scope's `@`, a quote, or a colon joining an option or a
  revision to the path
- **THEN** the command is refused
- **AND** the reason names where the path resolves

#### Scenario: A word that runs on past the workspace's name at a dividing character is judged whole

- **WHEN** a piece of a shell command's word resolves to the workspace itself, and the word carries
  that piece's last name on through a character that divides it into pieces, naming a sibling of
  the workspace
- **THEN** the command is refused

#### Scenario: A glob that can match the parent directory is refused

- **WHEN** a path component is a pattern beginning with a dot that can match the parent directory,
  and the path it forms that way resolves outside the workspace
- **THEN** the command is refused

#### Scenario: The null device may be named

- **WHEN** a bash command redirects to or names the null device or a standard stream
- **THEN** that word does not make the command refused
- **AND** a PowerShell command naming the same path is still judged as a path

#### Scenario: Another drive glued to a relative path is refused in either dialect

- **WHEN** on a platform with drive letters, a Bash or PowerShell command names a letter, a colon
  and a relative path with a separator, such as `Z:foo/bar`, where the letter is not the
  workspace's drive
- **THEN** the command is refused as outside the workspace
- **AND** the reason names the drive with its path

#### Scenario: The home-directory shorthand after a colon is refused as uncheckable

- **WHEN** a bash command names a word such as `of=c:~/y`, whose piece after a colon begins with the
  home-directory shorthand
- **THEN** the command is refused with a reason saying where it points cannot be checked

#### Scenario: A backslash an inner shell removes is judged as removed

- **WHEN** a command hands an inner shell a quoted word such as `.\./x`, which that shell reads as
  `../x`
- **THEN** the command is refused

#### Scenario: A glob an inner shell expands through a link is refused

- **WHEN** a command hands an inner shell a quoted glob pattern that shell would expand to an entry
  of the workspace that is a link resolving outside it
- **THEN** the command is refused

#### Scenario: A bracket expression at a word's edge is judged as a glob

- **WHEN** a shell command names a glob whose bracket expression begins or ends the word, such as
  `[u]p/x` or `sub/[a]`, and the pattern matches an entry of the workspace that is a link resolving
  outside it
- **THEN** the command is refused
- **AND** the reason names where the matched entry resolves

#### Scenario: A parent-directory step after a globbed link is judged from the link's target

- **WHEN** a shell command names a glob that matches a link inside the workspace, followed by a
  parent-directory step, such as `sub/l*/..` with `sub/l` a link to the workspace root
- **THEN** the command is refused
- **AND** the reason names the directory that step reaches, not only the pattern as written

#### Scenario: An extended pattern group that can match the parent directory is refused

- **WHEN** a shell command names an extended pattern group, such as `@(..)/x`, one of whose
  alternatives begins with a dot, and the parent directory it can match is outside the workspace
- **THEN** the command is refused
- **AND** the reason names the word as written

#### Scenario: A backslash removed by two shells in turn is judged as removed

- **WHEN** a command hands one inner shell a word that a second inner shell reads as a traversal
  only after each has removed a level of backslash escapes, such as `.\\./x`
- **THEN** the command is refused

#### Scenario: The null device inside a script's text is a path on a platform with drive letters

- **WHEN** on a platform with drive letters, a bash command's word holds the null device's name
  inside a quoted script, not as a whole word or a redirect target
- **THEN** that name is judged as a path

#### Scenario: A provider-qualified path is judged by the path it names

- **WHEN** a PowerShell command names `Microsoft.PowerShell.Core\FileSystem::` followed by a path
  outside the workspace
- **THEN** the command is refused

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
