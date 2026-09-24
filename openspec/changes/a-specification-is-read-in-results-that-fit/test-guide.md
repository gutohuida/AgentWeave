# Test guide — a specification is read in results that fit

## Agent-verifiable

1. **Bounded.** Task 1.1 fails before the fix (paste the measured size) and passes after it.
2. **Complete.** Task 1.2: repeated reads, following `remaining_identifiers`, return every
   requirement exactly once. Continuations carry no preamble, and task 1.15 shows a large preamble does
   not push the read count past `ceil(total / budget) + 1`. Task 1.14: every name in
   `omitted_sections` is readable with `include=<name>`.
3. **In the route's own order.** Task 1.3 fails if the fit appends in payload order.
4. **Addressable by id.** Task 1.7 fails before the fix with the exact F363 refusal.
5. **Skew-safe.** Task 1.11. Then, by hand, point the new `mcp_server.read_spec_document` at a Hub
   running the pre-change route (checkout of `ce086b6` on `:8010`) and confirm that a default read
   still succeeds.
6. **Live.** Task 3.1 on `:8010`, with a Haiku agent: no spill and no guard refusal.

## Human-only

1. On a real project after `:8000` restarts, open an agent's transcript for a turn that read a large
   approved specification. The `read_spec_document` result is inline, with no "Output saved to …"
   notice. If it was truncated, the agent's next call names the remaining identifiers.
