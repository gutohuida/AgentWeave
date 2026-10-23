"""2026-10-23 Checkpoints sweep: checkpoint grants across agents (scratch Hub :8112, profile ck1023).
Real Haiku turns. alpha works and leaves notes, the operator presses Checkpoint now, then beta
calls list_checkpoints / read_checkpoint / recall closed, with can_read_checkpoints, then with
can_recall too. The tool results are read from beta's turns, not from beta's summary.

  AW_P=proj-... py -3.11 scripts/drive/s1023_ck_grants.py alpha|press|beta <label>|grant <field> <bool>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_ck_lib import B, P, e2e, q, req, show  # noqa: E402

STATE = pathlib.Path(e2e.os.environ["AW_E2E_ROOT"]) / "grants.json"


def _state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def _save(**kw):
    s = _state()
    s.update(kw)
    STATE.write_text(json.dumps(s, indent=1))


def _turn(agent, msg, fresh=False):
    rid = e2e.cmd_turn(P, agent, msg, perm="workspace", fresh=fresh)
    print("status", e2e.wait_for(rid, 8))
    e2e.dump_turn(rid)
    return rid


def alpha():
    rid = _turn("alpha", "Read src/calc.py and tests/test_calc.py and say in two sentences what is wrong; "
                "do not edit anything. Then call the AgentWeave tool submit_checkpoint_notes with intent "
                "'calc.add subtracts; fix pending in src/calc.py' and warnings ['do not touch tests/test_calc.py'].",
                fresh=True)
    conv = q("select conversation_id from runs where id=?", rid)[0]["conversation_id"]
    _save(conv=conv)
    print("CONV", conv)


def press():
    conv = _state()["conv"]
    st, ck = show("POST", f"{B}/conversations/{conv}/checkpoint", {}, 4000)
    if st < 300:
        _save(checkpoint=ck["id"])
    st, r = req("GET", f"{B}/checkpoints/{ck.get('id')}/rendered")
    print("RENDERED", st, json.dumps(r, ensure_ascii=False)[:2500])


def beta(label):
    s = _state()
    ck = s["checkpoint"]
    obs = s.get("observation", "obs-unknown")
    _turn("beta", f"[{label}] Call these AgentWeave tools in order and quote each raw result in one line: "
          f"1) list_checkpoints with no arguments; 2) read_checkpoint with checkpoint_id '{ck}'; "
          f"3) recall with observation_id '{obs}'. Do nothing else.", fresh=True)


def grant(field, value):
    show("PATCH", f"{B}/agents/beta", {field: value == "true"}, 800)


def obs(oid):
    _save(observation=oid)


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
