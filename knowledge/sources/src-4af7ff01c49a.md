Decision on contradiction ctr-9e1fffe15449, between two facts of the vault:
- fct-7cff2b4e5a2b: "The hub-tests command should be set to `py -3.11 -m pytest hub/tests -q -p no:cacheprovider -n auto --timeout=600`."
- fct-d0d934cef195: "The checks must be entered exactly as written, because `cd hub` and `set PYTHONPATH=src` make each suite import the code in the checkout being checked rather than the main checkout's editable install."

The fact that stands is fct-7cff2b4e5a2b: "The hub-tests command should be set to `py -3.11 -m pytest hub/tests -q -p no:cacheprovider -n auto --timeout=600`.".

Note: The project's hub-tests check, as configured on 2026-10-28, is `py -3.11 -m pytest hub/tests -q -n auto --dist loadgroup -p no:cacheprovider --timeout=600` from the repository root, with a 3600 s timeout. The 10-24 `cd hub ... tests/ --dist loadfile --timeout=300` form was replaced by it on 10-26; checks of a task worktree still import that worktree's code and pass.
