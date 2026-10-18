"""SPIKE: print each change transition as it happens; exit when all three tasks are approved/rejected or after N minutes."""
import sqlite3, sys, time
DB = r"C:\Users\huida\.agentweave\hub\profiles\spike1018\agentweave.db"
minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 25
seen = set()
end = time.time() + minutes * 60
while time.time() < end:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    for r in c.execute("select t.sequence, k.title, t.from_status, t.to_status, t.actor_kind, coalesce(t.actor_agent,'-'), k.stage_index, coalesce(k.assignee,'-') from task_transitions t join tasks k on k.id=t.task_id order by t.sequence"):
        if r[0] not in seen:
            seen.add(r[0]); print(time.strftime("%H:%M:%S"), *r[1:], flush=True)
    rows = c.execute("select status from tasks where spec_document_id is not null").fetchall()
    c.close()
    if rows and all(s in ("approved", "rejected") for (s,) in rows):
        print("ALL SETTLED"); break
    time.sleep(30)
