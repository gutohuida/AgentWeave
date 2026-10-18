"""SPIKE: write the three variant payloads (default dev->test, dev only, dev->security->test)."""
import json, sys

VARIANTS = {
    "a": ("Default dev then test", None, "qa"),
    "b": ("Dev only, quick and dirty", [], None),
    "c": ("Dev then security then test", [
        {"key": "security", "agent": "sec",
         "duty": "Check the change for security problems only: injection, unsafe eval, path traversal, secrets. Approve if none; otherwise revision_needed naming each problem."},
        {"key": "test", "agent": "qa",
         "duty": "Run the module's tests (`py -3.11 -m unittest`) and check each acceptance criterion. Approve if they pass."},
    ], None),
}
v = sys.argv[1]
title, stages, tester = VARIANTS[v]
fn = {"a": "slugify", "b": "clamp", "c": "safe_join"}[v]
k = fn.replace("_", "-")
desc = {
    "slugify": "Create slug_a.py with slugify(text) -> str: lowercase, spaces and punctuation become single hyphens, no leading/trailing hyphen. Add test_slug_a.py (unittest) covering three cases.",
    "clamp": "Create clamp_b.py with clamp(x, lo, hi) -> number returning x bounded to [lo, hi]. Add test_clamp_b.py (unittest) covering three cases.",
    "safe_join": "Create join_c.py with safe_join(base, name) -> str that joins a file name onto a base directory and raises ValueError if the result would escape base (e.g. '../x'). Add test_join_c.py (unittest) covering a normal name and an escaping one.",
}[fn]
delivery = {"mode": "flow", "agent": "dev", "stop_when_queue_empties": True, "cron": "*/1 * * * *"}
if tester:
    delivery["tester"] = tester
if stages is not None:
    delivery["stages"] = stages
doc = {
    "schema_version": 1, "kind": "change-spec", "title": f"Spike {v}: {title}",
    "summary": f"Spike variant {v} of editable flow stages: one tiny task.",
    "problem": "Throwaway tracer for the editable-flow-stages spike.",
    "requirements": [{"key": f"{k}-works", "statement": f"{fn} behaves as described and has passing unittest tests.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": f"{k}-tests-pass", "requirement": f"{k}-works", "given": "the repository", "when": "`py -3.11 -m unittest` runs", "then": "all tests pass", "how_to_check": "py -3.11 -m unittest", "checked_by": "agent"}],
    "tasks": [{"key": f"build-{k}", "title": f"Build {fn}", "description": desc, "requirements": [f"{k}-works"]}],
    "delivery": delivery,
}
print(json.dumps({"document": doc}))
