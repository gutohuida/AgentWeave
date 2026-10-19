"""Ledger sweep, phase 3: Checkpoint now on builder's conversation, the notes it carried, cut-over;
then the ledger against Accounting and the task story.

py -3.11 scripts/drive/s1019_ledger_p3.py
"""

import time

from s1019_ledger_lib import S, api, ro, save, say, wait_run

P, C1, T1 = S["P"], S["C1"], S["T1"]

# let rev's message turn finish first
for r in ro("select id from runs where project_id=? and status in ('running','queued','starting','pending')", (P,)):
    print("waiting", r["id"], wait_run(r["id"], 600))

t0 = time.time()
st, cp = api("POST", f"/projects/{P}/conversations/{C1}/checkpoint", timeout=600)
say(f"checkpoint now ({time.time() - t0:.0f}s)", (st, cp))
if st < 300:
    S["CP1"] = cp["id"]
    save()
st, cps = api("GET", f"/projects/{P}/conversations/{C1}/checkpoints")
say("checkpoints", (st, cps))
st, notes = api("GET", f"/projects/{P}/conversations/{C1}/checkpoint-notes")
say("notes after checkpoint", (st, notes))
if S.get("CP1"):
    st, rendered = api("GET", f"/projects/{P}/checkpoints/{S['CP1']}/rendered")
    say("rendered", (st, rendered))
    st, cut = api("POST", f"/projects/{P}/checkpoints/{S['CP1']}/cutover")
    say("cutover", (st, cut))
    if st < 300:
        S["C2"] = cut["successor_conversation_id"]
        save()
    st, again = api("POST", f"/projects/{P}/checkpoints/{S['CP1']}/cutover")
    say("cutover again", (st, again))
    st, notes2 = api("GET", f"/projects/{P}/conversations/{S.get('C2', C1)}/checkpoint-notes")
    say("successor notes", (st, notes2))
st, nope = api("GET", f"/projects/{P}/conversations/conv-nope/checkpoint-notes")
say("notes unknown conv", (st, nope))

# --- ledger vs accounting vs story
st, led = api("GET", f"/projects/{P}/ledger")
say("ledger", (st, led))
st, acc = api("GET", f"/projects/{P}/accounting")
say("accounting", (st, acc))
st, story = api("GET", f"/projects/{P}/tasks/{T1}/story")
say("story", (st, story))
say("turn_usage", ro("select run_id, agent, total_tokens, api_equivalent_usd_micros, observed_at from turn_usage where project_id=?", (P,)))
say("worker_invocations", ro("select id, kind, total_tokens, cost_usd_micros, created_at from worker_invocations where project_id=?", (P,)))
say("messages", ro("select id, sender, recipient, subject, task_id from messages where project_id=?", (P,)))
