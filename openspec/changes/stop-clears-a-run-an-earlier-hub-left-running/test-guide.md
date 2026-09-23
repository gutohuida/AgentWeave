# Test guide — Stop clears a run an earlier Hub left running

## Agent-verifiable

1. **Stop clears it.** Tasks 1.1 and 1.2 fail before (409, then *already has a run in progress*) and
   pass after.
2. **A surviving process is ended first.** Task 1.3, with a real sleeper process.
3. **Failures leave the run as it was and say so.** Tasks 1.4 (409) and 1.5 (500).
4. **This process's own window is untouched.** Control 1.6.
5. **Startup is untouched.** Control 1.7.
6. **The busy reasons name Stop.** Task 1.8.
7. **Live.** Task 3.1 reproduces the state F168 described and clears it with the real button.

## Human-only

1. Start a long turn on a trial Hub, kill only the Hub process, start it again. The agent reads as
   busy and a new message waits; the waiting line now says the run was left by an earlier Hub and
   that Stop clears it. Press **Stop** in the conversation header. The turn is marked *interrupted*,
   the agent's process is gone (check Task Manager), and the waiting message starts.
2. Press Stop on an agent whose turn this Hub started a moment ago: it behaves exactly as before.
