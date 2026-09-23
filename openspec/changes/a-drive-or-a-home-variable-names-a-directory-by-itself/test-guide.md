# Test guide — a drive or a home variable names a directory by itself

## Agent-verifiable

| What | How | Passes when |
|---|---|---|
| Another drive is refused in PowerShell | `py -3.11 -m pytest hub/tests/test_permission_approver.py -q` (tasks 1.1, 1.3; Windows) | `Z:`, `Z:foo`, `-Destination:Z:`, `Temp:` refused, naming the word with its colon |
| Revisions and bash stand | same (task 1.2) | `HEAD:README.md`, `s:a:b:`, the workspace's own drive, Bash `C:` allowed |
| Home and temp variables are uncheckable | same (task 1.4) | the reason says "cannot be checked" |
| Ordinary shell stands | same (task 1.5) | `echo $x`, loops, `'$HOME'`, `$(…)` and the commit heredoc allowed |
| Nothing else moved | full `hub/tests/` (task 2.4) | count recorded |

## Human-only

1. Ask an agent under the default posture to "copy notes.md to your home directory". **Expect:**
   whether it writes `~`, `$HOME` or `$env:USERPROFILE`, a refusal saying where it points cannot be
   checked.
2. Ask it to commit its work. **Expect:** the commit goes through (the heredoc form is untouched).
3. On a machine with a second drive, ask a PowerShell-using agent to copy a file to `D:`.
   **Expect:** refused as outside.
