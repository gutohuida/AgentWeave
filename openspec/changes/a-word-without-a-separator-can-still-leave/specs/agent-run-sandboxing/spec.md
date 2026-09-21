## ADDED Requirements

### Requirement: A word with no path separator is still judged when it names a directory by itself

Under the posture in which the Hub decides each tool call against the run's workspace, a word of a shell command that contains no path separator but names the parent directory, or begins with the home-directory shorthand, or carries either as an option's value within the same word, SHALL be judged rather than exempted as not a path.

A word with no path separator usually names an entry of the directory the shell runs in, so it
cannot leave the workspace, and judging every such word would cost a resolution per word for no
gain. Two spellings are exceptions, because each names a directory entirely by itself. The parent
directory, `..`, is the directory above. The home-directory shorthand, alone or followed by a user
name, a sign or a number, is a home or remembered directory that the shell substitutes when it
runs. A boundary that refuses `../` and allows `..` has not drawn a boundary, since the two name the
same directory.

A word that names the parent directory SHALL be judged by where it resolves against the workspace,
exactly as the same word followed by a separator is judged. Where it resolves outside the
workspace, the refusal SHALL say so and name the word.

A word that begins with the home-directory shorthand SHALL be refused with a reason saying where it
points cannot be checked, as a word that begins with the shorthand and contains a separator already
is. It SHALL NOT be refused with a reason claiming it is outside the workspace.

An option can carry its value in its own word, with no separator between them: a short option with
its value glued on, or, in a dialect that joins a parameter's name to its value with a colon, that
form. A value carried that way that names the parent directory SHALL be judged as the parent
directory, and the refusal SHALL name the whole word. Where the dialect's shell resolves the
home-directory shorthand in such a value, a value that begins with it SHALL be refused as
uncheckable. This is what the requirement that a word joining a path to an option be judged at
least as strictly as the path alone asks of these spellings.

The word judged is the argument the shell passes on. An argument ends at a NUL character, so a word
the shell decodes into the parent directory followed by a NUL and more characters SHALL be judged
as the parent directory.

An ordinary word with no path separator, such as a file name in the directory the shell runs in, an
option, the current directory, a name made of three or more dots, or a revision, SHALL still be
allowed. This requirement does not claim that every other separator-less word stays inside the
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

- **WHEN** a shell command passes the parent directory as the value of an option, joined to the
  option's name by an equals sign, by the dialect's parameter colon, or glued to a short option
  with nothing between them, and that directory is outside the workspace
- **THEN** the command is refused
- **AND** the reason names the whole word as the command wrote it

#### Scenario: The parent directory ended by a NUL is refused

- **WHEN** a shell command names a quote form that decodes to the parent directory followed by a
  NUL character and further characters, and that directory is outside the workspace
- **THEN** the command is refused

#### Scenario: The home-directory shorthand alone is refused as uncheckable

- **WHEN** a shell command, in either dialect, names a word that begins with the home-directory
  shorthand and contains no path separator
- **THEN** the command is refused
- **AND** the reason states that where the word points cannot be checked
- **AND** the reason does not state that the word is outside the workspace

#### Scenario: The home-directory shorthand as a parameter's value is refused as uncheckable

- **WHEN** a PowerShell command passes a value that begins with the home-directory shorthand to a
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
