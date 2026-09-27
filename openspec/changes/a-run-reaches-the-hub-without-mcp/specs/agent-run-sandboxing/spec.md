## ADDED Requirements

### Requirement: The Hub's own call command is decided like the Hub's own tools

Wherever the Hub answers a run's permission request, it SHALL allow, in every posture and without asking the operator, a shell command that is exactly one invocation of the call command and a file write of an arguments file inside the run's own calls directory, and SHALL decide every other request exactly as it would without this rule.

The plane's operations were never subject to the run's posture: the tool-protocol tools are allowed
by standing, because asking a person to approve each message would make collaboration unusable and
each call is already bounded by the run's own credential. The call command reaches the same
operations under the same credential, and nothing else, so it has the same standing. Its arguments
must be written to a file first, and that write is part of the same call.

"Exactly one invocation" is read from the command's text in the shell it will run in: the command
name `aw-tool` by itself (not a path to it), then an operation the command can perform, then at most
one arguments file given as a plain relative path to a `.json` file inside the run's calls directory
within its workspace, and nothing else. Any command separator, pipe, redirection, substitution,
variable reference or pattern character anywhere in the command, or a second command, means it is
not one invocation. The calls directory is the Hub's own, and the repository ignores it.

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

#### Scenario: An arguments file elsewhere is not a plain call

- **WHEN** the arguments file named is outside the run's calls directory, reaches it through `..`, is
  absolute, or is not a `.json` file
- **THEN** the request is decided as it would be without this rule

#### Scenario: A path to the command is not the command

- **WHEN** a run names the command by a path, such as `./aw-tool` or a full path
- **THEN** the request is decided as it would be without this rule

#### Scenario: A write that only resolves into the calls directory through a link is not allowed by it

- **WHEN** a written path resolves, after links are followed, outside the run's calls directory
- **THEN** the write is decided as it would be without this rule

### Requirement: A Claude run pre-allows the Hub's call command

Every non-yolo Claude run the Hub spawns SHALL allow the call command by standing in the harness's own tool allowlist, in both its shell tools, whether or not the Hub's tool-protocol server is configured.

A Claude run whose approver is not there cannot be asked about anything, so a request that needs
approval is denied. On the path without the Hub's server, that is every shell command, and a
plane reachable only through a shell command is unreachable (F301). Allowing the call command by
standing makes the plane reachable there without making anything else reachable.

#### Scenario: The allowlist names the call command

- **WHEN** the Hub spawns a non-yolo Claude run, with or without its own tool-protocol server
- **THEN** the command line allows the call command in the harness's bash tool and its PowerShell tool

#### Scenario: Nothing else is allowed by it

- **WHEN** such a run runs a shell command that is not the call command
- **THEN** it is decided as it would be without this allowlist entry
