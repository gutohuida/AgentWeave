# Test guide — input the Hub accepted is answered as accepted

## Agent-verifiable

1. **A queued message is not answered as a failure.** Task 1.1 fails today (500) and passes after.
2. **Something drains it.** Tasks 1.2 and 1.3: the retry calls the scheduler again, and after it
   gives up the deferred set holds the agent until the next request.
3. **A lost event record changes nothing.** Task 1.4.
4. **A turn that already started is reported as started.** Task 1.5.
5. **The same at every route that queues input.** Task 1.6.
6. **The backstop cannot lose a pair.** Task 1.7.
7. **Refusals are untouched.** Task 1.8.
8. **Live** (3.1): a held write lock gives a 200 `queued`, and the turn starts when the lock goes.

## Human-only

1. From the composer, send to an agent while the Hub is busy writing (a checkpoint, say). The send
   never shows an error for a message that then appears in the conversation.
