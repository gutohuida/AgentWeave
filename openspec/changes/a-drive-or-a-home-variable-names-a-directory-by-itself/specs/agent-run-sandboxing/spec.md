## MODIFIED Requirements

### Requirement: A word with no path separator is still judged when it names a directory by itself

Under the posture in which the Hub decides each tool call against the run's workspace, a word of a shell command that contains no path separator but names the parent directory, is the home-directory shorthand in a form the shell substitutes, is a reference to a variable that names a directory by itself, names a link or is a glob that can match one, or names a drive, or carries any of these as an option's value within the same word, SHALL be judged rather than exempted as not a path.

A word with no path separator usually names an entry of the directory the shell runs in, so it
cannot leave the workspace unless that entry is a link, and resolving every such word would cost a
resolution per word for no gain. Two spellings are exceptions, because each names a directory entirely by itself. The parent
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

An ordinary word with no path separator, such as a file name in the directory the shell runs in
that is not a link out of the workspace, an option, the current directory, a name made of three or more dots, a revision, the shorthand before
a number or a figure, or the shorthand carried by an option where the dialect's shell does not
resolve it, SHALL still be allowed.

A reference to a variable that the shell, the PowerShell host or the platform sets for every
process to one directory names that directory by itself, exactly as the home-directory shorthand
does. Such variables include the home directory and its drive and path, the current or previous
working directory, the temporary directory, the per-user and machine-wide application data
directories, the public and synced user folders, the system and program directories, the directories
a Linux desktop names under home, and PowerShell's own home, install directory and profile. A
reference to one SHALL be refused with a reason saying where it points cannot be checked, when it
begins the word or an option's value, or follows a colon within it, and no name character follows it,
since whatever is joined on names that directory or a sibling of it. This holds for every spelling
the dialect accepts for the reference, including braces, a scope or provider prefix, and a nested
command interpreter's percent form, and in a bash command for PowerShell's environment spelling,
which a nested PowerShell expands. In PowerShell an environment variable is referenced only through
the environment provider; a script variable that merely shares an environment variable's name, such
as `$TEMP` or a user's `$tmp`, is not that directory and is one of the other variables below. A reference the outer shell will not expand, because it is
quoted literally or escaped, SHALL be refused as well, because the word may be handed to an inner
shell that expands it and the judge cannot tell text from a command handed on. A word whose text
before its first expansion is the parent directory, or whose text with every expansion removed is
the parent directory, starts in the parent whatever the expansions yield, and SHALL be refused as
uncheckable.

A word with no path separator that names an entry of the directory the shell runs in that is a link
SHALL be judged by where the link resolves, and so SHALL such a name glued to a short option. A
separator-less glob pattern SHALL be judged by the entries it matches as well as by its text, so
that a match that is a link is judged by where it resolves.

In PowerShell, and in either dialect on a platform with drive letters (where a Bash command hands
its words to native programs too), a word made of one drive letter and a colon, optionally followed
by a name with no separator, names that drive's current location, and, where that drive exists,
SHALL be judged by where it resolves: on
another drive it is outside the workspace, on the workspace's own drive it is the directory the
shell runs in. On a platform with drive letters, where the platform reports that no such drive
exists, the word is an ordinary name, since nothing can be written there. A check of the drive that
fails for any other reason SHALL count the drive as existing, so that a failure never allows a word
naming a real drive. Whether the word is judged as a drive or not, the other checks of this
requirement still apply to it. In the PowerShell dialect, PowerShell's temporary drive SHALL be judged as the temporary directory; in a bash command the same text is an ordinary word. A word with a
second colon, or a longer name before the colon, such as a revision and a path, is not a drive. In
bash on a platform without drive letters these words are ordinary names.

The home-directory shorthand after a colon in a word's value, such as `of=c:~`, SHALL be refused as
uncheckable, because a shell expands it there in an assignment-shaped word. A separator-less word or
option value that is a glob pattern beginning with two dots and able to match the parent directory,
such as `..*`, SHALL be judged as the parent directory, because a shell that does not skip the dot
entries expands it to include the parent. A pattern beginning with one dot, such as `.*`, is not
judged this way when it has no separator: it is as often a quoted regular expression, which the
judge cannot tell from a glob.

This requirement does not claim that every other separator-less word stays inside the workspace. A
reference to any other variable, including one a tool or the user sets, and a command substitution,
become a directory only when the shell runs; such a word is not judged, and an answer that allows it
SHALL NOT be read as a statement that it stays inside.

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

#### Scenario: A directory variable referenced alone is refused as uncheckable

- **WHEN** a shell command, in either dialect, names a separator-less word or option value that
  begins with, or has after a colon, a reference to a variable the platform sets to one directory,
  such as the home, working, previous working, temporary, public or program-data directory
- **THEN** the command is refused
- **AND** the reason states that where the word points cannot be checked

#### Scenario: A directory variable handed to an inner shell is refused

- **WHEN** a shell command names such a reference inside single quotes or escaped, as it would be
  handed to an inner shell, for example `bash -c 'cp n $HOME'`
- **THEN** the command is refused as uncheckable

#### Scenario: Every spelling of a directory variable is refused

- **WHEN** a PowerShell command names such a variable in braces, with an environment, variable or
  scope prefix, or a command names it in a nested command interpreter's percent form
- **THEN** the command is refused as uncheckable

#### Scenario: A nested PowerShell's environment reference is refused in a bash command

- **WHEN** a bash command hands a nested PowerShell a reference to a directory variable in
  PowerShell's environment spelling, such as `powershell -c 'Copy-Item x $env:TEMP'`
- **THEN** the command is refused as uncheckable

#### Scenario: A PowerShell variable sharing an environment variable's name stands

- **WHEN** a PowerShell command names a variable without the environment provider whose name is
  also an environment variable's, or a user variable, such as the `$tmp` in
  `$tmp = New-TemporaryFile; Remove-Item $tmp`
- **THEN** that word does not make the command refused

#### Scenario: Any other bare expansion stands

- **WHEN** a shell command names a separator-less word that is a reference to any other variable,
  including a lowercase user variable or one whose name only begins with a directory variable's
  name, or a command substitution whose text names no directory variable
- **THEN** that word does not make the command refused

#### Scenario: The parent directory left by an expansion is refused

- **WHEN** a shell command names a separator-less word whose text, with every expansion removed, is
  the parent directory, such as `$x..` or `$(true)..`
- **THEN** the command is refused as uncheckable

#### Scenario: A link named by itself is judged by where it resolves

- **WHEN** a shell command names, with no separator, an entry of the workspace that is a link
  resolving outside it, alone, as an option's value, or glued to a short option
- **THEN** the command is refused
- **AND** the reason names where the link resolves

#### Scenario: A separator-less glob that matches a link out of the workspace is refused

- **WHEN** a shell command names a separator-less glob pattern that matches an entry of the
  workspace that is a link resolving outside it
- **THEN** the command is refused

#### Scenario: A separator-less bracket glob that matches a link is refused

- **WHEN** a shell command names a separator-less glob whose bracket expression begins or ends the
  word, such as `[u]p` or `u[p]`, and it matches an entry of the workspace that is a link resolving
  outside it
- **THEN** the command is refused

#### Scenario: The parent directory before an expansion is refused

- **WHEN** a shell command names a separator-less word that begins with the parent directory
  followed immediately by an expansion
- **THEN** the command is refused as uncheckable

#### Scenario: Another drive is outside

- **WHEN** a PowerShell command names a word that is a drive letter and a colon, with or without a
  following name, and that drive exists and is not the workspace's drive
- **THEN** the command is refused
- **AND** the reason names the word with its colon

#### Scenario: A glob that can match the parent directory is judged as the parent

- **WHEN** a shell command names a separator-less word such as `..*`, or a brace pattern expanding
  to one such as `.{,.}*`
- **THEN** the command is refused as outside the workspace
- **AND** a separator-less `.*` does not make the command refused, unless one of its matches is a
  link resolving outside the workspace

#### Scenario: The home-directory shorthand after a colon is refused as uncheckable

- **WHEN** a bash command names a separator-less word such as `of=c:~` or `PATH=a:~`
- **THEN** the command is refused with a reason saying where it points cannot be checked

#### Scenario: Another drive is outside in a Bash command on a platform with drive letters

- **WHEN** on a platform with drive letters, a Bash command names a word that is a drive letter and
  a colon, and that drive exists and is not the workspace's drive
- **THEN** the command is refused

#### Scenario: A drive letter that names no drive is an ordinary word

- **WHEN** on a platform with drive letters, a command in either dialect names a word that is one
  letter and a colon, such as `e:` in `except Exception as e:` or `a:` in `jq '{a: .x}'`, and the
  platform reports that no drive with that letter exists
- **THEN** that word does not make the command refused

#### Scenario: A drive whose check fails is treated as existing

- **WHEN** on a platform with drive letters, the check of whether a drive exists fails for a reason
  other than the drive not existing, and the drive is not the workspace's drive
- **THEN** a word naming that drive is judged as that drive, and the command is refused

#### Scenario: A directory variable after the workspace's drive is still refused

- **WHEN** on a platform with drive letters, a command names a word such as `of=c:$HOMEPATH`, where
  the drive exists and is the workspace's drive, or `e:$HOMEPATH`, where no drive E exists
- **THEN** the command is refused as uncheckable

#### Scenario: The temporary drive is PowerShell's only

- **WHEN** a bash command names the word `temp:`, for example as a key in a heredoc
- **THEN** that word is not judged as the temporary directory

#### Scenario: A revision with a colon is not a drive

- **WHEN** a PowerShell command names a revision followed by a colon and a path, or a word with more
  than one colon
- **THEN** that word is not judged as a drive
