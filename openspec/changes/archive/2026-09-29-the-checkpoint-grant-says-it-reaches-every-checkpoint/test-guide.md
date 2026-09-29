# Test guide — the checkpoint grant says it reaches every checkpoint

## Agent-verifiable

1. **The hint states the real reach.** Task 1.1 fails before and passes after.
2. **The API no longer offers a field that never meant anything.** Task 1.2.
3. **Access is unchanged.** Controls 1.3: every access rule that held still holds, and a granted peer
   still reads across conversations, which is what F235 measured and what the grant now says.
4. **The migration round-trips.** Task 1.4.
5. **Live.** Task 4.1.

## Human-only

1. Open an agent's settings, *Checkpoints* section. The *Read other agents' checkpoints* hint now
   says the grant covers every conversation in this project, and no longer mentions each checkpoint's
   visibility.
2. After the operator's own `:8000` next restarts on this change, the app opens normally and
   checkpoints list and open as before (the migration dropped a column nothing read).
