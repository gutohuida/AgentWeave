# Test guide — a flow is configured from its own tab

## Agent-verifiable

1. **The default agent can be changed, and on a loop it waits for the next firing.** Tasks 1.1-1.3.
   1.3 is the mutation that proves staging matters, on a loop that declares no document: applied at
   once, a Run press starts a second firing beside the running one. (On a flow with a free agent that
   is already allowed, so 1.3 would prove nothing there.)
2. **A switch away from an agent that cannot work takes effect** (design D2a). Tasks 1.3a, 1.3b.
   An applied edit is recorded even when the firing then raises (1.3c).
   1.3a fails on R1's version, where a held agent refused every tick before the edit was applied.
3. **Bad agents are refused, only the operator can change a job's agent, and a plain job does not
   resume the old agent's session, and neither does a loop's first firing under its new agent.**
   Tasks 1.4, 1.4a, 1.5, 1.2a, 1.9.
4. **Nothing moves with the agent.** Task 1.6.
5. **A document can find its flow.** Task 1.7, and 3.5(e)'s phase-bar test in the route's own order
   and shape (no archived rows in the default listing).
6. **The panel sends only what changed, a revert is sent, and the dialog makes a flow, not a loop.**
   Task 3.5(a)-(d). **The document names its new flow at once.** Task 3.5(f).

## Human-only

1. On a trial Hub, open an approved document with no flow: **Start a flow…** appears. Start one,
   choosing an agent. The document now shows **Flow: <name>** without a reload, and opening it shows
   the flow's tab. Do this once on the Spec destination and once in a conversation's panel. From the
   Spec destination the link lands on the flow agent's view with the loop's tab in front, and Back
   returns to the document.
2. In that tab, change the cadence and the default agent. The cadence is in force at once; the agent
   shows under "From the next firing". After one firing, it is in force, and the jobs list names the
   new agent without a reload.
3. Try to save an archived agent: the reason is shown and nothing changes.
4. Know the skew: until `:8000` restarts on this code, an agent change from its reloaded page is
   refused, and a document that has a flow still offers **Start a flow…** (which is then refused).
