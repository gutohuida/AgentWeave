# Test guide — a word without a separator can still leave

## Agent-verifiable

Each check is automated. It runs without a Hub or a real agent turn.

| What | How | Passes when |
|---|---|---|
| `..` is refused in both dialects | `py -3.11 -m pytest hub/tests/test_permission_approver.py -q` (tasks 1.1, 1.2) | the new rows are refused with "is outside your workspace", naming `'..'` |
| `~` is refused as uncheckable | same file (task 1.3) | the reason names the variable/`~` wording and never "outside" |
| P7 flipped | same file (task 1.4) | `cp notes.md $'..\x00x'` is refused |
| Nothing else moved | same file (task 1.5) plus the full `hub/tests/` suite (task 2.4) | the negative controls stay allowed; the full-suite count is recorded |
| Real shells agree | task 3.1, in a scratch directory | `cp notes.md ..` really lands outside in Git Bash and PowerShell |

## Human-only

These need a real run on the operator's own Hub, after the change ships and a run's MCP server has
restarted.

1. Give an agent under the workspace posture a task whose obvious first move is to write a file into
   the parent directory, for example "copy notes.md next to the workspace folder". **Expect:** the
   tool call is refused, and the reason quotes `'..'` and says it is outside the workspace. It is not
   silently allowed.
2. Ask it to list your home directory with `ls ~`. **Expect:** a refusal saying where `'~'` points
   cannot be checked.
3. Ask for an ordinary in-workspace command such as `ls -la` or `git log HEAD~1`. **Expect:** it runs
   with no refusal.

If step 1 is allowed, the MCP server serving that run predates the change. Restart the run before
reporting a defect.
