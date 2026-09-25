# Test guide — a flow is configured from its own tab

## Agent-verifiable

1. **The default agent can be changed, and on a loop it waits for the next firing.** Tasks 1.1-1.3.
   1.3 is the mutation that proves staging matters: applied at once, a Run press starts a second
   firing beside the running one.
2. **Bad agents are refused, and a plain job does not resume the old agent's session.** Tasks 1.4, 1.5.
3. **Nothing moves with the agent.** Task 1.6.
4. **A document can find its flow.** Task 1.7, and 3.5's phase-bar test in the route's own order.
5. **The panel sends only what changed, and the dialog makes a flow, not a loop.** Task 3.5.

## Human-only

1. On a trial Hub, open an approved document with no flow: **Start a flow…** appears. Start one,
   choosing an agent. The document now shows **Flow: <name>**, and opening it shows the flow's tab.
2. In that tab, change the cadence and the default agent. The cadence is in force at once; the agent
   shows under "From the next firing". After one firing, it is in force.
3. Try to save an archived agent: the reason is shown and nothing changes.
4. Know the skew: until `:8000` restarts on this code, an agent change from its reloaded page is
   refused, and a document that has a flow still offers **Start a flow…** (which is then refused).
