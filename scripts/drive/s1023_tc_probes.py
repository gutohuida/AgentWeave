"""2026-10-23 Traces row: what each traces route answers on bad input, and keyset paging walked end to end.

  py -3.11 scripts/drive/s1023_tc_probes.py [probes|paging|clear]
"""

import json
import sys
import urllib.parse

from s1023_tc_lib import B, e2e, q, req, say


def show(method, path, body=None, limit=600):
    st, res = req(method, path, body)
    print(f"{method} {path} {json.dumps(body) if body is not None else ''} -> {st} {json.dumps(res, default=str)[:limit]}")
    return st, res


def raw_export(params=""):
    import urllib.error
    import urllib.request

    url = f"{e2e.hub()}/api/v1{B}/traces/export{params}"
    r = urllib.request.Request(url, headers={"Authorization": f"Bearer {e2e.key()}"})
    try:
        with urllib.request.urlopen(r) as resp:
            body = resp.read()
            try:
                parsed = json.loads(body)
                spans = len(parsed["resourceSpans"][0]["scopeSpans"][0]["spans"])
                logs = len(parsed["resourceLogs"][0]["scopeLogs"][0]["logRecords"])
                return resp.status, f"valid JSON, {spans} spans, {logs} logs, {len(body)} bytes"
            except Exception as exc:  # noqa: BLE001
                return resp.status, f"NOT JSON ({exc}): {body[:200]!r}"
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:300].decode("utf-8", "replace")


def probes():
    show("GET", "~/traces/0123456789abcdef0123456789abcdef")
    show("GET", "~/traces/not-a-trace-id")
    show("GET", "~/traces/by-run/run-nope")
    show("GET", "~/traces/by-run/run-nope?limit=0")
    show("GET", "~/traces?limit=0")
    show("GET", "~/traces?limit=201")
    show("GET", "~/traces?before=garbage")
    show("GET", "~/traces?before=x|y")
    show("GET", "~/traces?operation=" + "x" * 33)
    show("GET", "~/traces?operation=no.such.kind")
    show("GET", "~/traces?run_id=run-nope")
    show("GET", "~/traces?task_id=task-nope")
    for params in ("?since=garbage", "?since=2026-13-01", "?since=2026-10-23&until=2026-10-23",
                   "?since=2026-10-24&until=2026-10-23", "?since=2099-01-01", "?until=2000-01-01",
                   "?since=2026-10-23T25:00:00"):
        print("GET export" + params, "->", *raw_export(params))
    show("DELETE", "~/traces?since=garbage")
    show("DELETE", "~/traces?since=2026-10-24&until=2026-10-23")
    show("DELETE", "~/traces?since=2099-01-01")
    secret_header = "Bearer quokka-header-value-7781"
    for body in (
        {"otlp_endpoint": "ftp://collector"},
        {"otlp_endpoint": "http://"},
        {"otlp_endpoint": "x" * 1025},
        {"export_enabled": True},
        {"otlp_headers": {"bad:name": "v"}},
        {"otlp_headers": {" ": "v"}},
        {"otlp_headers": "Authorization=" + secret_header},
        {"otlp_headers": {"Authorization": [secret_header]}},
        {"record_reads": "maybe"},
        {"no_such_field": 1},
        [],
    ):
        show("PUT", "~/traces/settings", body, limit=900)
    show("GET", "~/traces/settings")
    # Is the header value from a refused body anywhere in the trace store?
    n = q("select count(*) n from trace_spans where instr(coalesce(attributes,'')||coalesce(events,''), ?) > 0", "quokka-header-value")
    say("refused header value in trace_spans", n)
    n = q("select count(*) n from event_logs where instr(coalesce(data,''), ?) > 0", "quokka-header-value")
    say("refused header value in event_logs", n)
    st, r = req("GET", "~/traces?limit=20&operation=aw.request")
    for t in r["traces"]:
        if "settings" in t["name"] and "traces" in t["name"]:
            st, d = req("GET", f"~/traces/{t['trace_id']}")
            print("  request trace", d["root"]["name"], d["root"]["status"], d["root"]["status_message"],
                  json.dumps(d["root"]["attributes"])[:300])


def paging():
    full = []
    st, r = req("GET", "~/traces?limit=200")
    full = [t["trace_id"] for t in r["traces"]]
    say("full list", [len(full), r.get("next_before")])
    seen, before, pages = [], None, 0
    while True:
        path = "~/traces?limit=3" + (f"&before={urllib.parse.quote(before)}" if before else "")
        st, r = req("GET", path)
        pages += 1
        if st != 200:
            say(f"page {pages} {st}", r)
            break
        seen += [t["trace_id"] for t in r["traces"]]
        before = r.get("next_before")
        if not before or pages > 200:
            break
    say("paged", {"pages": pages, "seen": len(seen), "unique": len(set(seen)), "same_order": seen == full[: len(seen)],
                  "missing": len(set(full) - set(seen))})
    # A cursor written with another offset: the same instant.
    st, r = req("GET", "~/traces?limit=200")
    mid = r["traces"][len(r["traces"]) // 2]
    stamp = mid["start_time"]
    say("mid", stamp)
    from datetime import datetime, timedelta, timezone

    at = datetime.fromisoformat(stamp)
    shifted = at.astimezone(timezone(timedelta(hours=2))).isoformat()
    for cursor in (f"{stamp}|{mid['root_span_id']}", f"{shifted}|{mid['root_span_id']}", f"{stamp.replace('+00:00', '')}|{mid['root_span_id']}"):
        st, r2 = req("GET", "~/traces?limit=200&before=" + urllib.parse.quote(cursor))
        older = [t["trace_id"] for t in r2.get("traces", [])] if st == 200 else r2
        expect = full[full.index(mid["trace_id"]) + 1:]
        print("cursor", cursor, "->", st, "count", len(older) if isinstance(older, list) else older, "expected", len(expect),
              "match" if older == expect else "MISMATCH")


def clear():
    show("GET", "~/traces/settings")
    show("DELETE", "~/traces")
    show("DELETE", "~/traces")
    show("GET", "~/traces/settings")
    show("GET", "~/traces?limit=50&operation=aw.request")


if __name__ == "__main__":
    {"probes": probes, "paging": paging, "clear": clear}[sys.argv[1] if len(sys.argv) > 1 else "probes"]()
