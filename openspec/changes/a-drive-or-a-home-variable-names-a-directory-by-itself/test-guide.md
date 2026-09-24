# Test guide — a drive or a home variable names a directory by itself

## Agent-verifiable

Runs after `the-shell-judge-reads-a-word-whole` is built. The Windows-only rows run in its
`hub-judge-windows` CI job, and every other row runs on Linux too.

| What | How | Passes when |
|---|---|---|
| Another drive is refused | `py -3.11 -m pytest hub/tests/test_permission_approver.py -q` (tasks 1.1, 1.3, 1.5b; Windows) | `Z:`, `Z:foo`, `-Destination:Z:`, `Temp:` refused, naming the word with its colon, where Z is an **existing** drive other than the workspace's (the runner's, or a `subst` drive the test makes and removes) |
| **A letter with no drive is an ordinary word** (operator, `B4-drive-exists`) | same (task 1.5c) | with `_drive_exists` patched on both platforms, and with the real probe on Windows when E and A are absent: `except Exception as e:` in a heredoc and `jq '{a: .x, b: .y}' f` allowed; a probe that raises anything but `FileNotFoundError` counts as existing; `c:$HOMEPATH` (own drive) and `e:$HOMEPATH` (no drive E) still refused as uncheckable |
| Revisions and bash stand | same (task 1.2) | `HEAD:README.md`, `s:a:b:`, the workspace's own drive, Bash `C:` allowed |
| Home and directory variables are uncheckable, in every spelling | same (tasks 1.4, 1.4b, 1.4c) | the reason says "cannot be checked" for `$HOME`, `$HOMEPATH`, `$PUBLIC`, `${env:TEMP}`, `$variable:HOME`, `$PROFILE`, `c:$HOMEPATH`… |
| **The same variable handed to an inner shell is refused** (R4) | same (task 1.4d) | `bash -c 'cp n $HOME'`, `sh -c "cp n \$HOME"`, `powershell -c 'Copy-Item x $HOME'` refused |
| A `..` that survives an expansion is refused (R4) | same (task 1.4e) | `$x..`, `$(true)..`, `.$x.` refused |
| **A link named by itself is refused** (R4) | same (task 1.4f), with a real link or junction | `cp n up`, `cp n u*`, `cp -tup n` refused, naming where `up` resolves; an inside link allowed |
| Ordinary shell stands | same (task 1.5) | `echo $x`, loops, `$tmp`, `$(git rev-parse --show-toplevel)` and the commit heredoc allowed |
| The accepted costs are what was accepted | same (task 1.5a) | `echo '$HOME'`, `cp x $(dirname $PWD)` and a heredoc naming `$HOME` refused |
| Nothing else moved | full `hub/tests/` (task 2.4) | count recorded |

## Human-only

1. Ask an agent under the default posture to "copy notes.md to your home directory". **Expect:**
   whether it writes `~`, `$HOME`, `$env:USERPROFILE`, `$HOMEDRIVE$HOMEPATH` or
   `bash -c 'cp notes.md $HOME'`, a refusal saying where it points cannot be checked.
2. Ask it to commit its work. **Expect:** the commit goes through (the heredoc form is untouched).
   If its message names `$HOME`, expect a refusal. The agent should then write the message to a file
   and use `git commit -F`.
3. On a machine with a second drive, ask a PowerShell-using agent to copy a file to `D:`.
   **Expect:** refused as outside. Then ask it to run a short Python script containing
   `except Exception as e:` through a heredoc, on a machine with no drive E. **Expect:** it runs.
   With a USB stick or card mounted as E, the same script is refused as drive E, the accepted
   residual.
4. (R4) In a scratch project, make a junction inside the agent's workspace that points outside
   (`New-Item -ItemType Junction -Path lnk -Target <outside dir>`), and ask the agent to
   `cp notes.md lnk`. **Expect:** a refusal naming where `lnk` resolves. Delete the junction.
