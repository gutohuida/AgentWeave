"""Record the Vault page's fixtures from a project's own vault and Hub database, read-only.

    py -3.11 mock/record_vault.py C:/Users/huida/.agentweave/hub/data/agentweave.db proj-d85a82bf4216 C:/Users/huida/Documents/projects/AgentWeave

Writes three files into mock/fixtures/ (gitignored, like every recorded fixture):

- vault_project_map.json  `GET /vault/map` as the Hub answers it: `vault.build_map` over the project's
                          knowledge/ folder, shaped by `vault_access.shape` with the database's read
                          counts and readers. Private text held elsewhere is left out (no private root).
- vault_fact_uses.json    the proposed `GET /vault/fact-uses`: per fact, the spec requirements that cite
                          it (a requirement's `facts`) and the conflicts the newest spec-vault-check
                          firing of each document found with it, kept only while that requirement still
                          says what it was judged against (`vault_spec_check.document_warnings`'s rule).
- vault_texts.json        each tracked text source's whole text, so the mock can show what the proposed
                          `GET /vault/search` would find inside documents.
- vault_fact_citations.json  each tracked fact's claim and citations (its record under knowledge/facts),
                          so the reader marks a fact's lines as the app's fact reads do.

The database is opened with `mode=ro` and the project's files are only read.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "fixtures"
sys.path.insert(0, str(HERE.parents[1]))

from hub import spec_identity, vault, vault_access  # noqa: E402


def requirements_of(stored):
    """`vault_spec_check.requirements_of`, restated: that module opens the Hub's database on import."""
    if not isinstance(stored, dict) or not isinstance(stored.get("requirements"), list):
        return []
    identifiers, _ = spec_identity.read_identity(stored)
    listed = []
    for raw in stored["requirements"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("key"), str):
            continue
        facts = raw.get("facts") if isinstance(raw.get("facts"), list) else []
        listed.append(
            {
                "key": raw["key"],
                "identifier": identifiers.get(raw["key"]),
                "statement": raw.get("statement") if isinstance(raw.get("statement"), str) else "",
                "facts": [f for f in facts if isinstance(f, str)],
            }
        )
    return listed


def iso(value: str) -> str:
    return value.replace(" ", "T") + "Z" if "T" not in value else value


def main(db_path: str, project_id: str, root_arg: str) -> None:
    root = Path(root_arg)
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    counts = {
        entry: (count, iso(last))
        for entry, count, last in db.execute(
            "select entry_id, count, last_fetched_at from vault_fetches where project_id = ?", (project_id,)
        )
    }
    readers: dict = {}
    for entry, agent, count, last in db.execute(
        "select entry_id, agent, count, last_read_at from vault_readers where project_id = ? "
        "order by last_read_at desc, agent",
        (project_id,),
    ):
        readers.setdefault(entry, []).append({"agent": agent, "count": count, "last_read_at": iso(last)})
    entries = vault_access.shape(vault.build_map(root, root / ".no-private-root"), counts, readers)
    facts = {e["id"] for e in entries if e["kind"] == "fact"}

    documents = {}
    for path in sorted((root / "spec").glob("**/spec.json")):
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        documents[path.relative_to(root).as_posix()] = stored

    uses: dict = {}

    def use(fact: str) -> dict:
        return uses.setdefault(fact, {"fact": fact, "citations": [], "conflicts": []})

    for doc, stored in documents.items():
        title = stored.get("title") or doc
        for requirement in requirements_of(stored):
            for fact in dict.fromkeys(requirement["facts"]):
                if fact in facts:
                    use(fact)["citations"].append(
                        {"document": doc, "title": title, "requirement": requirement["identifier"], "statement": requirement["statement"]}
                    )

    newest: dict = {}
    for (data,) in db.execute(
        "select data from event_logs where project_id = ? and event_type = 'manager_job_fired' "
        "and json_extract(data, '$.job') = 'spec-vault-check' order by timestamp, id",
        (project_id,),
    ):
        fired = json.loads(data)
        doc = (fired.get("subject") or {}).get("document")
        if doc:
            newest[doc] = fired
    for doc, fired in newest.items():
        stored = documents.get(doc)
        by_key = {r["key"]: r for r in requirements_of(stored)}
        for conflict in fired.get("conflicts") or []:
            requirement = by_key.get(conflict.get("requirement"))
            if requirement is None or requirement["statement"] != conflict.get("statement"):
                continue
            if conflict.get("fact") not in facts:
                continue
            use(conflict["fact"])["conflicts"].append(
                {
                    "document": doc,
                    "title": (stored or {}).get("title") or doc,
                    "requirement": requirement["identifier"],
                    "statement": requirement["statement"],
                    "explanation": (conflict.get("explanation") or "").strip(),
                    "checked_at": fired.get("ended_at") or fired.get("started_at"),
                }
            )

    texts = {}
    for entry in entries:
        if entry["kind"] != "source":
            continue
        text_file = root / "knowledge" / "sources" / f"{entry['id']}.md"
        if text_file.is_file():
            texts[entry["id"]] = text_file.read_text(encoding="utf-8", errors="replace")

    citations = {}
    for fact in facts:
        record_file = root / "knowledge" / "facts" / f"{fact}.json"
        if record_file.is_file():
            record = json.loads(record_file.read_text(encoding="utf-8"))
            citations[fact] = {"claim": record.get("claim"), "citations": record.get("citations") or []}

    OUT.mkdir(exist_ok=True)
    (OUT / "vault_fact_citations.json").write_text(json.dumps(citations), encoding="utf-8")
    (OUT / "vault_project_map.json").write_text(json.dumps({"entries": entries}, indent=1), encoding="utf-8")
    (OUT / "vault_fact_uses.json").write_text(json.dumps({"uses": list(uses.values())}, indent=1), encoding="utf-8")
    (OUT / "vault_texts.json").write_text(json.dumps(texts), encoding="utf-8")
    sources = sum(1 for e in entries if e["kind"] == "source")
    print(f"{sources} sources, {len(facts)} facts, {len(uses)} facts used by specs, {len(texts)} texts")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
