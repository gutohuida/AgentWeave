Decision on contradiction ctr-9cbe2c3796c0, between two facts of the vault:
- fct-7cff2b4e5a2b: "The hub-tests command should be set to `py -3.11 -m pytest hub/tests -q -p no:cacheprovider -n auto --timeout=600`."
- fct-dd4d98e08ae4: "Check 5 is `hub-tests`, with command `cd hub && py -3.11 -m pytest tests/ -q -n auto --dist loadfile --timeout=300 --timeout-method=thread -p no:cacheprovider` and a 3600 s timeout, taking about 24 minutes."

The fact that stands is fct-7cff2b4e5a2b: "The hub-tests command should be set to `py -3.11 -m pytest hub/tests -q -p no:cacheprovider -n auto --timeout=600`.".

Note: The project's hub-tests check, as configured on 2026-10-28, is `py -3.11 -m pytest hub/tests -q -n auto --dist loadgroup -p no:cacheprovider --timeout=600` from the repository root, with a 3600 s timeout. The 10-24 `cd hub ... tests/ --dist loadfile --timeout=300` form was replaced by it on 10-26; checks of a task worktree still import that worktree's code and pass.
