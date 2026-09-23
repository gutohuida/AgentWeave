# Test guide — the shell judge reads a word whole

## Agent-verifiable

No Hub and no agent turn needed.

| What | How | Passes when |
|---|---|---|
| Ordinary shell stops being refused | `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q` (task 1.1) | globs, `@scope/pkg`, `HEAD:path`, `%h/%s`, regexes and `2>/dev/null` are allowed |
| Brace patterns are judged as expanded | same file (tasks 1.2, 1.3) | `.{,.}`, `{.,.}.`, `.{,.}/x`, `src/{a,..}/../y` refused; quoted or escaped braces literal |
| A glob cannot reach the parent | same file (task 1.4) | `.*/x`, `../*` refused, naming the whole piece |
| Schemeless remotes are network addresses | same file (task 1.5) | `git@github.com:o/r.git`, `127.0.0.1:9/x` refused with the network reason |
| The judge always answers | same file (task 1.6) | no exception for pathological braces or brackets |
| Escapes stay refused | same file (task 1.7) plus `test_permission_approver.py` (task 1.8) | every negative control refused; only the listed rows moved |
| Nothing else moved | full `hub/tests/` (task 2.4) | count recorded |

## Human-only

After the change ships, on the operator's Hub (on `:8000` the edited file is used from the next run):

1. Ask an agent under the default posture to "run the tests in `test/*.test.js` and silence stderr
   with `2>/dev/null`". **Expect:** no refusal.
2. Ask it to `npm install @types/node` or `git show HEAD:README.md`. **Expect:** no filesystem
   refusal (the install may still be refused if it names a URL).
3. Ask it to copy a file with `cp notes.md .{,.}/`. **Expect:** a refusal naming `'..'`.
4. Watch the activity log for refusals whose quoted word is a fragment of a longer word (for
   example `'/x'` out of `a/x`). **Expect:** none; report any.
