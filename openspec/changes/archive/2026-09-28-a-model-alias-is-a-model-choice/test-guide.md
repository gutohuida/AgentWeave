# Test guide — a model alias is a model choice

## Agent-verifiable

1. Tasks 1.1–1.4 and 1.6 fail before group 2 and pass after it.
2. `POST /projects/<p>/runners {"cli":"claude","model":"opus"}` answers 201, and `GET` returns it
   with `"model": "opus"` and `"model_unrecognised": false`.
3. Drive 3.1: the turn ran, `turn_usage.model` is a `claude-haiku-…` id, and `runners.model` is
   `haiku`. This is the proof that the alias reached the CLI as written and the CLI resolved it.
4. `POST … {"model":"claude-opus-9"}` still answers 400, and the sentence names the aliases.

## Human-only

1. Open Runners, then New runner, and choose `claude`. Is the difference between
   `opus — latest (now Opus 5.5)` and `Opus 5.5` clear enough to choose between without reading
   docs?
2. Open an existing runner stored as an alias. It should show the alias selected and no
   *Unrecognised* chip.
3. Add agent with provider `claude`: the same `Latest` group appears.
