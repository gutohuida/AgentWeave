"""C2: a check's output with a non-ASCII character reaches the sent-back note as itself, not as
U+FFFD (`project_checks._run_one`)."""

import sys

from hub import project_checks

PY = f'"{sys.executable}"'


def _run(command, tmp_path):
    return project_checks._run_one(
        {"name": "c", "command": command, "timeout_seconds": 60}, tmp_path
    )


def test_an_ellipsis_a_python_check_prints_survives(tmp_path):
    script = tmp_path / "say.py"
    script.write_text("print('assert abcde\\u2026 == abc...')\n", encoding="utf-8")
    result = _run(f'{PY} "{script}"', tmp_path)
    assert "abcde…" in result["output_tail"], result["output_tail"]


def test_a_check_writing_the_windows_code_page_is_decoded_as_it(tmp_path):
    script = tmp_path / "say.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write('abcde\\u2026\\n'.encode('cp1252'))\n",
        encoding="utf-8",
    )
    result = _run(f'{PY} "{script}"', tmp_path)
    assert "abcde…" in result["output_tail"], result["output_tail"]
