## ADDED Requirements

### Requirement: A word with no path separator is still judged when it names a directory by itself

Under the posture in which the Hub decides each tool call against the run's workspace, a word of a shell command that contains no path separator but names the parent directory, or begins with the home-directory shorthand, SHALL be judged rather than exempted as not a path.

A word with no path separator usually names an entry of the directory the shell runs in, so it
cannot leave the workspace, and judging every such word would cost a resolution per word for no
gain. Two spellings are exceptions, because each names a directory entirely by itself. The parent
directory, `..`, is the directory above. The home-directory shorthand, alone or followed by a user
name or a sign, is a home or remembered directory that the shell substitutes when it runs. A
boundary that refuses `../` and allows `..` has not drawn a boundary, since the two name the same
directory.

A word that names the parent directory SHALL be judged by where it resolves against the workspace,
exactly as the same word followed by a separator is judged. Where it resolves outside the
workspace, the refusal SHALL say so and name the word.

A word that begins with the home-directory shorthand SHALL be refused with a reason saying where it
points cannot be checked, as a word that begins with the shorthand and contains a separator already
is. It SHALL NOT be refused with a reason claiming it is outside the workspace.

The word judged is the argument the shell passes on. An argument ends at a NUL character, so a word
the shell decodes into the parent directory followed by a NUL and more characters SHALL be judged
as the parent directory.

Every other word with no path separator SHALL continue to stand without being judged as a path.

#### Scenario: The parent directory alone is refused

- **WHEN** a shell command, in either dialect, names the parent directory as a word of its own and
  that directory is outside the workspace
- **THEN** the command is refused
- **AND** the reason states that the word is outside the workspace and names it

#### Scenario: The parent directory and the parent directory followed by a separator are judged alike

- **WHEN** one shell command names the parent directory alone and another names it followed by a
  path separator, otherwise identical
- **THEN** both commands receive the same decision

#### Scenario: The parent directory assembled from quotes is refused

- **WHEN** a shell command writes the parent directory from pieces the shell joins by removing
  quotes between them
- **THEN** the command is refused

#### Scenario: The parent directory as an option's value is refused

- **WHEN** a shell command passes the parent directory as the value of an option, joined to the
  option's name by an equals sign
- **THEN** the command is refused

#### Scenario: The parent directory ended by a NUL is refused

- **WHEN** a shell command names a quote form that decodes to the parent directory followed by a
  NUL character and further characters
- **THEN** the command is refused

#### Scenario: The home-directory shorthand alone is refused as uncheckable

- **WHEN** a shell command, in either dialect, names a word that begins with the home-directory
  shorthand and contains no path separator
- **THEN** the command is refused
- **AND** the reason states that where the word points cannot be checked
- **AND** the reason does not state that the word is outside the workspace

#### Scenario: An ordinary name with no separator still stands

- **WHEN** a shell command names only words with no path separator that are neither the parent
  directory nor begin with the home-directory shorthand, including the current directory, a name
  made of three or more dots, a name containing two dots between other characters, and a revision
  that contains the shorthand after its first character
- **THEN** the command is allowed
