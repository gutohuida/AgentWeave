## ADDED Requirements

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
Windows uses to run command scripts, and the same text then runs something else. This rule cannot see
that, and it does not claim to; the earlier command was itself decided under the run's posture.
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
