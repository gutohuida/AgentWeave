"""How long a test's own `git` may take: one bound for every fixture and helper (AW-157).

A test's setup git (`init`, `config`, `add -A`, `commit`) is not what any test measures. On the
machine the Hub's landing checks run on, with twenty suite workers and live agents beside them,
`git config user.email` and `git add -A` each ran past the 30 s every helper used to pass, and 17
tests in one landing batch failed on that alone (lbat-73ef33ce098d, 2026-11-16); every one passed
when re-run serially. A git that is genuinely stuck still fails, naming its command, well inside
the suite's 600 s per-test limit. `test_test_git_shares_one_timeout.py` keeps every git call under
`hub/tests` on this constant rather than a literal.
"""

GIT_TIMEOUT = 300
