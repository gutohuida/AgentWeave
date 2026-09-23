# Test guide — an agent's tool server is the one its Hub loaded

## Agent-verifiable

1. **An edit after start does not reach a spawn.** Task 1.1 fails today and passes after. It is the
   finding's shape in one assertion: the source changes, the pin does not.
2. **The pin heals, it never falls back.** Tasks 1.2 and 1.4: a deleted or altered copy is restored
   from memory; a copy that cannot be written raises, and the caller never gets the source path.
3. **The trigger names the pin.** Task 1.5 fails today (the command names `hub/hub/mcp_server.py`).
4. **A failed pin is a refusal with a sentence.** Task 1.6: 409, no `Run`, the entry still queued
   with the reason.
5. **The served surface is the pinned program.** Task 1.7 passes before and after.
6. **Live, on a trial Hub** (3.1, 3.2): the spawned path is the pinned one, and an edit to the
   checkout's file during the Hub's life leaves the pinned bytes unchanged.

## Human-only

1. **After the operator restarts `:8000` onto this change**, the Hub's startup log names the pinned
   path. Nothing else should look different: agents keep their tools.
2. The operator decides when `:8000` restarts. Until then it still spawns its checkout's file, and
   F363's `mcp_server.py` half should wait for that restart (design D6).
