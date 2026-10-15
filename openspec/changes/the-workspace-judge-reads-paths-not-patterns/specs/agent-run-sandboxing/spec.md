## ADDED Requirements

### Requirement: A pattern a PowerShell comparison operator matches against is not a path in the command

When the Workspace posture's judge reads a command in the PowerShell dialect, it SHALL NOT judge
as a path, and SHALL NOT refuse as uncheckable, a quoted literal that is the pattern operand of a
binary comparison operator in an expression-mode statement. Every other word in the command SHALL
be judged exactly as the requirement *"A path in a shell command is judged by where it resolves"*
requires. This requirement takes precedence over that requirement only for such an operand.

The terms are defined as follows:

- **Expression-mode statement.** A statement or pipeline element whose first token is a variable,
  a quoted string, a number, `(`, `@(` or `$(`. The body of a `{ }` script block is a statement
  list of its own. An element that begins with a command name, `&` or `.` is command mode, and no
  word in it is exempt.
- **The operators.** `-match`, `-notmatch`, `-like`, `-notlike`, `-replace` and `-split`, with
  their `c` and `i` prefixes, matched case-insensitively. The operator MUST directly follow an
  operand, so a unary `-split` is not covered.
- **The pattern operand.** The quoted literal that directly follows the operator. For `-replace`
  it is only the first element, and the replacement MUST still be judged.
- **A quoted literal.** A single-quoted string, or a double-quoted string that contains no `$` and
  no backtick. The literal MUST contain no PowerShell quote character of any kind — neither an
  ASCII `'` or `"` nor a Unicode smart quote (`‘ ’ ‚ ‛ “ ” „`) — so that a string the lexer reads
  as closed cannot in fact be closed earlier by PowerShell, leaving a real path after it unjudged.

The Bash reading SHALL NOT apply this exemption. A tool key that is read in both dialects SHALL
remain refused whenever either reading refuses.

#### Scenario: The drive's recursive listing that filters out .git is allowed

- **GIVEN** the Workspace posture and a workspace that contains a `.git` directory
- **WHEN** the PowerShell tool runs `Get-ChildItem -Recurse -Force -File | Where-Object {
  $_.FullName -notmatch '\\.git\\' } | Resolve-Path -Relative`
- **THEN** the call is allowed
- **AND** the same call with `'\\.git(\\|$)'` as the pattern is allowed

#### Scenario: A regex quantifier in the pattern does not make it a path

- **GIVEN** the Workspace posture and a workspace that contains a `.git` directory
- **WHEN** the PowerShell tool runs `$ip -match '\d{1,3}'`, whose pattern holds a regex brace
  quantifier beside a `\`
- **THEN** the call is allowed, because the whole operand is exempt and no part of it is judged as
  a path even after brace expansion
- **AND** the same pattern as an argument in command mode, `Copy-Item $x -notmatch '\d{1,3}'`, is
  refused

#### Scenario: A comparison operator in command mode protects nothing

- **WHEN** the PowerShell tool runs `Write-Output $x -match 'C:\outside'`, or `robocopy $x -match
  'C:\outside'`
- **THEN** the call is refused, because `C:\outside` is outside the workspace

#### Scenario: A replacement, a unary split, a format operand, and a split's left operand are values, not patterns

- **WHEN** the PowerShell tool runs `Set-Content -Path ('x' -replace 'x','C:\outside\f') -Value y`,
  or `Set-Content -Path (-split 'C:\outside\f')[0] -Value y`, or `Remove-Item ('{0}' -f
  'C:\outside\f')`, or `'C:\outside\f' -split '\\'`
- **THEN** the call is refused, because none of these quoted literals is the pattern operand of a
  listed operator: a `-replace` replacement, a unary `-split` operand, a `-f` format argument (the
  `-f` operator is not on the list), and a binary `-split`'s left operand are all judged as paths

#### Scenario: Another statement in the same command is still judged

- **WHEN** the PowerShell tool runs `Where-Object { $_ -notmatch '\\.git\\' } | Copy-Item
  -Destination C:\outside`, or `Where-Object { Remove-Item C:\x }`
- **THEN** the call is refused

#### Scenario: An interpolated or unquoted operand is judged as today

- **WHEN** the PowerShell tool runs `$x -notmatch $env:TEMP`, or `$x -match "C:\o\$y"`
- **THEN** the call is refused, exactly as it is without this requirement

#### Scenario: The Bash reading and an unknown dialect stay strict

- **WHEN** the Bash tool runs `$x -match '/outside/f'`
- **THEN** the call is refused
- **AND** a Copilot shell call whose tool name was not reported, and which is therefore read in
  both dialects, is refused for the drive's listing exactly as it was before this requirement
