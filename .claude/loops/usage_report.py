"""Usage report for the autonomous windows, and for the whole subscription.

    py -3.11 .claude/loops/usage_report.py --windows [--since YYYY-MM-DD]
    py -3.11 .claude/loops/usage_report.py --all --since YYYY-MM-DD

--windows reads .claude/autonomous/usage-ledger.jsonl (one row per iteration, written by
run-iteration.ps1 from the run's own --output-format json result) and reports each window by item
kind and model. Where ~/.claude/usage-history.jsonl (written by the operator's statusline) holds a
weekly-% reading before and after a window, it prints the delta and the implied $ per 1% of the
weekly limit -- the calibration the operator asked for before any cap is set (2026-09-15).

--all reads every transcript under ~/.claude/projects and reports list-price-equivalent usage per
local day and source: windows, interactive sessions here, Hub agent workers, routines, and other
projects. Dollars are API list price; Anthropic does not publish how the subscription weights
input, cache and output, so read them as relative weights.

Stdlib only.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / ".claude" / "autonomous" / "usage-ledger.jsonl"
CLAUDE_HOME = Path.home() / ".claude"
HISTORY = CLAUDE_HOME / "usage-history.jsonl"
PROJECTS = CLAUDE_HOME / "projects"

# $ per million tokens (input, output). Cache read = 0.1x input, 1h write = 2x, 5m write = 1.25x.
# Checked 2026-09-15 against the CLI's own costUSD for Sonnet 5 and Haiku 4.5 (exact match).
PRICES = {"opus": (5.0, 25.0), "sonnet": (2.0, 10.0), "haiku": (1.0, 5.0), "fable": (10.0, 50.0)}

KIND_RE = re.compile(r"-(r\d+|rev|review|impl|drive|gate|archive)$", re.I)
WINDOW_PROMPT = "Continue the autonomous work session"


def family(model: str) -> str | None:
    for name in PRICES:
        if name in (model or ""):
            return name
    return None


def kind_of(item: str) -> str:
    m = KIND_RE.search(item or "")
    if m:
        k = m.group(1).lower()
        return "r" if re.fullmatch(r"r\d+", k) else k
    if (item or "").startswith("ledger-"):
        return "ledger"
    return item if item in ("compose",) else "other"


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    with contextlib.suppress(ValueError):
                        rows.append(json.loads(line))
    except OSError:
        pass
    return rows


def table(headers: list[str], rows: list[list]) -> str:
    cells = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    out = ["  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))]
    out.append("  ".join("-" * w for w in widths))
    for r in cells[1:]:
        pairs = enumerate(zip(r, widths, strict=True))
        out.append("  ".join(c.rjust(w) if i else c.ljust(w) for i, (c, w) in pairs))
    return "\n".join(out)


# --- --windows ------------------------------------------------------------------------------------


def weekly_at(history: list[dict], when: datetime, before: bool) -> tuple[float, datetime] | None:
    best = None
    for h in history:
        ts = parse_ts(h.get("captured_at"))
        pct = ((h.get("rate_limits") or {}).get("seven_day") or {}).get("used_percentage")
        if ts is None or not isinstance(pct, (int, float)):
            continue
        if before and ts <= when and (best is None or ts > best[1]):
            best = (float(pct), ts)
        if not before and ts >= when and (best is None or ts < best[1]):
            best = (float(pct), ts)
    return best


def report_windows(since: str | None, ledger: Path = LEDGER) -> None:
    rows = [r for r in read_jsonl(ledger) if not since or (r.get("started") or "") >= since]
    if not rows:
        print(f"No ledger rows in {ledger}" + (f" since {since}" if since else "") + ".")
        return
    history = read_jsonl(HISTORY)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[((r.get("started") or "")[:10], r.get("window") or "?")].append(r)

    calibrations = []
    for (day, window), its in sorted(groups.items()):
        cost = sum(r.get("total_cost_usd") or 0 for r in its)
        print(f"\n== {day} {window}: {len(its)} iterations, ${cost:.2f} list ==")
        by_kind: dict[tuple[str, str, str], list[float]] = defaultdict(list)
        for r in its:
            key = (kind_of(r.get("item") or ""), r.get("model") or "?", r.get("effort") or "-")
            by_kind[key].append(r.get("total_cost_usd") or 0)
        print(
            table(
                ["kind", "model", "effort", "n", "$ total", "$ mean"],
                [
                    [k, m, e, len(v), f"{sum(v):.2f}", f"{sum(v) / len(v):.2f}"]
                    for (k, m, e), v in sorted(by_kind.items(), key=lambda kv: -sum(kv[1]))
                ],
            )
        )
        by_model: dict[str, float] = defaultdict(float)
        for r in its:
            for model, u in (r.get("model_usage") or {}).items():
                by_model[model] += u.get("cost_usd") or 0
        if by_model:
            print(
                "by model: "
                + ", ".join(
                    f"{m} ${c:.2f}" for m, c in sorted(by_model.items(), key=lambda kv: -kv[1])
                )
            )
        flagged = [r for r in its if r.get("is_error") or r.get("subtype") not in (None, "success")]
        for r in flagged:
            print(
                f"  ! {r.get('started')} {r.get('item')}: {r.get('subtype')} is_error={r.get('is_error')}"
            )

        start = min(filter(None, (parse_ts(r.get("started")) for r in its)), default=None)
        end = max(filter(None, (parse_ts(r.get("ended")) for r in its)), default=None)
        if start and end:
            pre, post = weekly_at(history, start, True), weekly_at(history, end, False)
            if pre and post:
                delta = post[0] - pre[0]
                span = f"weekly {pre[0]:.0f}% @ {pre[1]:%m-%d %H:%M}Z -> {post[0]:.0f}% @ {post[1]:%m-%d %H:%M}Z"
                if delta > 0:
                    calibrations.append(cost / delta)
                    print(
                        f"{span}: +{delta:.0f} pts, ${cost / delta:.2f} per 1% (includes anything else run in that span)"
                    )
                else:
                    print(f"{span}: no rise (weekly reset in between, or readings too coarse)")
            else:
                print("weekly bracket: no statusline reading on one side of this window")
    if calibrations:
        calibrations.sort()
        print(
            f"\n$ per 1% of weekly, median of {len(calibrations)} window(s): ${calibrations[len(calibrations) // 2]:.2f}"
        )


# --- --all ----------------------------------------------------------------------------------------


def source_of(project_dir: str, first_prompt: str) -> str:
    if project_dir == "C--Users-huida":
        return "home"
    name = project_dir.replace("C--Users-huida-", "").replace("Documents-projects-", "")
    if name == "AgentWeave":
        return "window" if first_prompt.startswith(WINDOW_PROMPT) else "interactive"
    if "-claude-routines-" in project_dir:
        return "routine:" + name.split("routines-", 1)[-1].split("-", 1)[0]
    if "agentweave-worker" in name:
        return "hub-agent-workers"
    if "--agentweave-" in name:  # a Hub's agent worktree or task dir: <project>--agentweave-...
        owner = name.split("--agentweave-", 1)[0]
        return "drive-hub agents" if owner.startswith("AppData-Local-Temp") else f"{owner} agents"
    if name.startswith("AppData-Local-Temp-claude-"):
        return "scratch"
    return name


def first_user_text(entries: list[dict]) -> str:
    for e in entries:
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text") or ""
    return ""


def cost_of(model: str, usage: dict) -> float:
    fam = family(model)
    if not fam:
        return 0.0
    pin, pout = PRICES[fam]
    cc = usage.get("cache_creation") or {}
    w1h, w5m = cc.get("ephemeral_1h_input_tokens"), cc.get("ephemeral_5m_input_tokens")
    total_write = usage.get("cache_creation_input_tokens") or 0
    if w1h is None and w5m is None:
        w1h, w5m = 0, total_write
    return (
        (usage.get("input_tokens") or 0) * pin
        + (usage.get("cache_read_input_tokens") or 0) * pin * 0.1
        + (w1h or 0) * pin * 2
        + (w5m or 0) * pin * 1.25
        + (usage.get("output_tokens") or 0) * pout
    ) / 1_000_000


def report_all(since: str) -> None:
    since_dt = datetime.fromisoformat(since).astimezone()  # local midnight
    since_epoch = since_dt.timestamp()
    # A streamed message can be written on several lines under one id, the earlier ones with a
    # partial output count, so the LAST line per id is the one that counts.
    latest: dict[str, tuple[str, str, str, dict]] = {}
    for project in PROJECTS.iterdir() if PROJECTS.exists() else []:
        if not project.is_dir():
            continue
        for session_file in project.glob("*.jsonl"):
            if session_file.stat().st_mtime < since_epoch:
                continue
            entries = read_jsonl(session_file)
            source = source_of(project.name, first_user_text(entries))
            files = [(session_file, entries, source)]
            sub_dir = project / session_file.stem / "subagents"
            if sub_dir.is_dir():
                files += [
                    (f, read_jsonl(f), source + "/subagents") for f in sub_dir.glob("*.jsonl")
                ]
            for _, rows, label in files:
                for e in rows:
                    msg = e.get("message") or {}
                    usage, model = msg.get("usage"), msg.get("model") or ""
                    ts = parse_ts(e.get("timestamp"))
                    if not usage or not ts or ts < since_dt or model == "<synthetic>":
                        continue
                    key = msg.get("id") or e.get("requestId") or e.get("uuid")
                    latest[key] = (ts.astimezone().strftime("%Y-%m-%d"), label, model, usage)
    totals: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for day, label, model, usage in latest.values():
        bucket = totals[(day, label)]
        bucket["$"] += cost_of(model, usage)
        bucket["calls"] += 1
        bucket[family(model) or "other"] += cost_of(model, usage)
    if not totals:
        print(f"No transcript usage since {since}.")
        return
    days = sorted({d for d, _ in totals})
    for day in days:
        rows = [(label, v) for (d, label), v in totals.items() if d == day]
        rows.sort(key=lambda kv: -kv[1]["$"])
        print(f"\n== {day}: ${sum(v['$'] for _, v in rows):.2f} list ==")
        print(
            table(
                ["source", "calls", "$ list", "opus", "sonnet", "haiku", "fable"],
                [
                    [label, int(v["calls"]), f"{v['$']:.2f}"]
                    + [f"{v.get(f, 0):.2f}" for f in ("opus", "sonnet", "haiku", "fable")]
                    for label, v in rows
                    if v["$"] >= 0.005
                ],
            )
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--windows", action="store_true", help="per-window report from the ledger")
    mode.add_argument(
        "--all", action="store_true", help="whole-subscription report from transcripts"
    )
    ap.add_argument("--since", help="YYYY-MM-DD (required with --all)")
    ap.add_argument(
        "--ledger", type=Path, default=LEDGER, help="ledger path (default: this repo's)"
    )
    args = ap.parse_args()
    if args.all:
        if not args.since:
            ap.error("--all needs --since")
        report_all(args.since)
    else:
        report_windows(args.since, args.ledger)


if __name__ == "__main__":
    main()
