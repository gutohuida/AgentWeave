"""Second record for `a-spec-document-is-stored-as-its-payload`: convert a COPY of the real corpus.

d1010 builds its legacy corpus with this Hub's own `convert?to=html`, so its round trip is partly
self-consistent. This copies the repo's real spec/ (written by the pre-change Hub, no rows in a
fresh database) into a throwaway git project, opens it on a scratch Hub (:8097, fresh db, never
:8000 or :8010), and checks: convert to json converts every document with none skipped, GET /spec
renders each, and convert back restores the same .html set. Never touches the repo's own spec/.

    py -3.11 scripts/drive/d1010b_real_corpus.py
"""

import json
import pathlib
import shutil
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1010_spec_json as d  # noqa: E402

root = d.TMP / "project"
src = d.REPO / "spec"


def tree(base):
    return {p.relative_to(base).as_posix(): p for p in sorted(base.rglob("*")) if p.is_file()}


def run():
    shutil.copytree(src, root / "spec")
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "copy of spec"]):
        d.git(root, *cmd)
    before = tree(root / "spec")
    html = sorted(k for k in before if k.endswith(".html"))
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "realcorpus"})
    d.check("project opens", code in (200, 201), f"{code}")
    base = f"/projects/{project['id']}"
    code, out = d.api("POST", f"{base}/project/spec/convert?to=json", timeout=600)
    d.check("convert to json answers 200", code == 200, f"{code} {str(out)[:300]}")
    converted, skipped = out.get("converted", []), out.get("skipped", [])
    d.check("every .html document converted, none skipped",
            len(converted) == len(html) and not skipped,
            f"html={len(html)} converted={len(converted)} skipped={skipped[:5]}")
    after = tree(root / "spec")
    left = [k for k in after if k.endswith(".html")]
    d.check("no .html left, one spec.json per converted document",
            not left and sum(k.endswith(".json") for k in after) == len(html) + 1,
            f"left={left[:5]} json={sum(k.endswith('.json') for k in after)}")
    bad = []
    for item in converted:
        stem = item["to"].removesuffix(".json")
        code, page = d.api("GET", f"{base}/project/spec?path={urllib.parse.quote(stem + '.json')}")
        if code != 200 or "<html" not in str(page).lower():
            bad.append((item["to"], code))
    d.check("GET /spec renders every converted document", not bad, f"bad={bad[:5]} of {len(converted)}")
    code, listing = d.api("GET", f"{base}/project/documents")
    paths = [x.get("path") for x in listing["documents"]] if code == 200 else []
    # The list is rows-only and a fresh database has none for files a pre-change Hub wrote
    # (adoption makes them), so an empty list is expected here, not a finding.
    print(f"INFO rows listed for the rowless corpus: {len(paths)}")
    code, out = d.api("POST", f"{base}/project/spec/convert?to=html", timeout=600)
    d.check("convert back answers 200", code == 200 and not out.get("skipped"), f"{code} {str(out)[:200]}")
    back = tree(root / "spec")
    same_set = sorted(k for k in back if k.endswith(".html")) == html
    d.check("reverse restores the same .html set and no .json documents",
            same_set and not [k for k in back if k.endswith("spec.json")],
            f"missing={sorted(set(html) - set(back))[:5]}")
    identical = sum(before[k].read_bytes() == back[k].read_bytes() for k in html if k in back)
    print(f"INFO byte-identical after the round trip: {identical}/{len(html)}")
    import subprocess
    stat = subprocess.run(["git", "diff", "--stat", "--", "spec"], cwd=root, capture_output=True,
                          text=True).stdout.strip().splitlines()
    print("INFO git diff vs the copy:", stat[-1] if stat else "none")


def main():
    proc = d.start_hub()
    try:
        run()
    except d.Stop:
        pass
    finally:
        d.stop_hub(proc)
    bad = [n for n, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
