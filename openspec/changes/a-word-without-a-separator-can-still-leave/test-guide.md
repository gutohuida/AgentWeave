# Test guide — a word without a separator can still leave

## Agent-verifiable

Each check is automated. It runs without a Hub or a real agent turn.

| What | How | Passes when |
|---|---|---|
| `..` is refused in both dialects | `py -3.11 -m pytest hub/tests/test_permission_approver.py -q` (tasks 1.1, 1.2) | the new rows are refused with "is outside your workspace", naming `'..'` |
| A workspace at a filesystem root keeps `..` inside | same file (task 1.2, second case) | `cp notes.md ..` and `cp notes.md ../` are both allowed |
| `~` is refused as uncheckable | same file (task 1.3) | the reason says "cannot be checked" and never "outside" |
| P7 flipped | same file (task 1.4) | `cp notes.md $'..\x00x'` is refused |
| An option's joined value is judged | same file (task 1.5) | `cp -t.. notes.md`, `tar -C.. -xf a.tar` and `Copy-Item notes.md -Destination:..` are refused, naming the whole word; `-Destination:~` is refused as uncheckable (task 1.3) |
| The rows that pinned the old allow moved, and only those | same file (tasks 1.6, 1.7) plus task 2.3 | R8 and R9 are refused; H10 is refused naming `'..'`; H10b is refused as uncheckable; nothing else in the eight judge test files changed |
| Nothing else moved | same file (task 1.8) plus the full `hub/tests/` suite (task 2.4) | the negative controls stay allowed; the full-suite count is recorded |
| Real shells agree | tasks 3.1 and 3.2, in a scratch directory | `cp notes.md ..`, `cp -t.. notes.md` and `Copy-Item notes.md -Destination:..` really land outside; `...`, `C:` and `cp -t~` do not |

## Human-only

These need a real run on the operator's own Hub, after the change ships and a run's MCP server has
restarted. On `:8000` that happens as soon as the file changes on disk, because the Hub starts each
run's MCP server from this checkout (design R2-7).

1. Give an agent under the workspace posture a task whose obvious first move is to write a file into
   the parent directory, for example "copy notes.md next to the workspace folder". **Expect:** the
   tool call is refused, and the reason quotes `'..'` (or the whole option word, such as
   `'-Destination:..'`) and says it is outside the workspace. It is not silently allowed.
2. Ask it to list your home directory with `ls ~`. **Expect:** a refusal saying where `'~'` points
   cannot be checked.
3. Ask for an ordinary in-workspace command such as `ls -la` or `git log HEAD~1`. **Expect:** it runs
   with no refusal.
4. Watch for a refusal you did not expect in ordinary work, above all a quoted `~` used as a search
   pattern (`grep '~' file`) or a `cd ..` inside a longer command. **Expect:** the refusal names the
   word. Report it if it blocks work an agent had no other way to do; design D3 and Risks name the
   alternatives.

If step 1 is allowed, the MCP server serving that run predates the change. Restart the run before
reporting a defect.
