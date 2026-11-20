"""The app's text says profile, thread and run (FR-10 of `profiles-threads-and-builds-everywhere`).

Runs `scripts/checks/ui_vocabulary_check.py` over hub/ui/src, which is why this file is in the
sweep set: it reads the UI source rather than importing what it guards. The script is loaded by
path, as `test_ui_build_stamp.py` loads its script, so a failure names each leftover use.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "checks" / "ui_vocabulary_check.py"


def _check():
    spec = importlib.util.spec_from_file_location("ui_vocabulary_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_app_says_profile_thread_and_run_and_titles_its_settings_profiles():
    problems = _check().problems()
    assert not problems, "say profile, thread or run in the app (FR-10):\n" + "\n".join(problems)


def test_the_check_finds_each_kind_of_text_it_scans(tmp_path):
    check = _check()
    settings = tmp_path / "components" / "agents"
    settings.mkdir(parents=True)
    (settings / "AgentSettingsPage.tsx").write_text(
        "export const A = () => (\n"
        "  <div>\n"
        '    <h2 title="Agent settings">No conversation yet</h2>\n'
        "    <input aria-label=\"Conversation\" placeholder='Pick an agent' />\n"
        "    {name} has no conversation yet.\n"
        "    <Notice description={stale ? 'which is not an agent here' : `the ${x} agents`} />\n"
        "  </div>\n"
        ")\n"
        "const labels = [{ label: 'Agent' }]\n"
        "const url = `/api/v1/projects/${id}/agents`\n"
        "const data = { agent_name: agent, conversationId }\n",
        encoding="utf-8",
    )
    found = {use.text for use in check.uses(tmp_path)}
    assert found == {
        "Agent settings",
        "No conversation yet",
        "Conversation",
        "Pick an agent",
        "has no conversation yet.",
        "which is not an agent here",
        "the ${x} agents",
        "Agent",
    }
    problems = check.problems(tmp_path, tmp_path / "no-allowlist.txt")
    assert any("is not titled Profiles" in problem for problem in problems)


def test_an_allowlisted_line_that_no_longer_matches_fails(tmp_path):
    check = _check()
    allowlist = tmp_path / "allowlist.txt"
    allowlist.write_text("hub/ui/src/gone.tsx: Agent # gone\n", encoding="utf-8")
    problems = check.problems(check.UI_SRC, allowlist)
    assert any("no longer found" in problem for problem in problems)
