"""Sweep D vault phase 5: re-distil keeps fact ids (F587/F617); resolve for the non-presumed side (F640);
second resolve 409; re-distil the loser does not reopen (F586)."""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import mine, save, say, sc  # noqa: E402
m = mine(); b = m["base"]
def facts_of(src):
    mp = sc.api("GET", f"{b}/vault/map")[1]
    out = []
    def walk(n):
        if isinstance(n, dict):
            if n.get("kind") == "fact" and src in str(n.get("source", n.get("sources", ""))):
                out.append((n["id"], n.get("disputed"), n.get("superseded"), n.get("status")))
            for v in n.values(): walk(v)
        elif isinstance(n, list):
            for v in n: walk(v)
    walk(mp); return out
def nfirings(): return len(sc.api("GET", f"{b}/manager/activity")[1]["firings"])
say("map keys", list(sc.api("GET", f"{b}/vault/map")[1].keys()))
before = facts_of(m["doc_new"]); say("doc_new facts before", before)
n0 = nfirings()
say("redistil doc_new", sc.api("POST", f"{b}/vault/sources/{m['doc_new']}/distil"))
sc.poll(lambda: nfirings() >= n0 + 2, 180, 3)
after = facts_of(m["doc_new"]); say("doc_new facts after", after)
say("contr after redistil", [(c["id"], c["status"], c["facts"], c.get("presumed")) for c in sc.api("GET", f"{b}/vault/contradictions")[1]["contradictions"]])
c = sc.api("GET", f"{b}/vault/contradictions")[1]["contradictions"][0]
loser_side = [s for s in c["sides"] if not s["presumed"]][0]
say("resolve bad stands", sc.api("POST", f"{b}/vault/contradictions/{c['id']}/resolve", {"stands": "fct-nope", "note": "x"}))
say("resolve no note", sc.api("POST", f"{b}/vault/contradictions/{c['id']}/resolve", {"stands": loser_side["id"]}))
r = sc.api("POST", f"{b}/vault/contradictions/{c['id']}/resolve", {"stands": loser_side["id"], "note": "Finance reverted the June increase; 100/min is current."})
say("resolve", r)
say("resolve again", sc.api("POST", f"{b}/vault/contradictions/{c['id']}/resolve", {"stands": loser_side["id"], "note": "again"}))
say("contr after resolve", sc.api("GET", f"{b}/vault/contradictions")[1])
save({"ctr": c["id"], "stands": loser_side["id"]})
n0 = nfirings()
say("redistil old (winner src)", sc.api("POST", f"{b}/vault/sources/{m['doc_old']}/distil"))
say("redistil new (loser src)", sc.api("POST", f"{b}/vault/sources/{m['doc_new']}/distil"))
sc.poll(lambda: nfirings() >= n0 + 4, 240, 3)
for x in sc.api("GET", f"{b}/manager/activity")[1]["firings"][:5]:
    say("f", {k: x.get(k) for k in ("subject", "outcome", "detail")})
say("contr after redistil2", [(c["id"], c["status"], c["facts"], c.get("presumed"), [s.get("presumed") for s in c["sides"]]) for c in sc.api("GET", f"{b}/vault/contradictions")[1]["contradictions"]])
say("doc_new facts final", facts_of(m["doc_new"])); say("doc_old facts final", facts_of(m["doc_old"]))
