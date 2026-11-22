"""The UI speaks of profiles, threads and runs, not agents and conversations.

    py -3.11 scripts/checks/ui_vocabulary_check.py [--list]

Spec `profiles-threads-and-builds-everywhere`, FR-10 (D7). Scans the user-visible text of the app's
source under hub/ui/src -- JSX text, and the `label`, `title`, `aria-label` and `placeholder`
attributes given a literal -- for the words *agent* and *conversation*, and fails on any use not
allowed by `ui_vocabulary_allowlist.txt` beside this script. It also checks that the profile settings'
home, the Profiles tab (a profile's page sits under it), is titled Profiles.

Identifiers are not text: `agent_name`, `conversationId`, `AgentWeave` and the like never match,
because the words are matched whole. Test files and fixtures are not scanned. An allowlist line is
`<repo-relative path>: <the text as found>`; text the check cannot tell from data (a dashboard
column, a runner's own product name) is allowed there, one line each, with a `#` comment saying why.

Exit 0 when clean, 1 when a use is found (each printed as `path:line: text`). `--list` prints every
use, allowlisted ones included.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterator, NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_SRC = REPO_ROOT / "hub" / "ui" / "src"
ALLOWLIST = Path(__file__).resolve().with_name("ui_vocabulary_allowlist.txt")

#: The settings screen that configures agents, and the title it must carry.
# A profile's settings are its page under the Profiles tab (spec a-profile-s-pool-and-a-new-chat-can-
# use-any-model-of-any-provider, FR-13/FR-14): the tab's label is the title to check.
PROFILE_SETTINGS = "lib/navigation.ts"
PROFILE_SETTINGS_TITLE = "Profiles"

# Matched whole, so identifiers (`agent_name`, `conversationId`, `AgentWeave`) and file names
# (`AGENTS.md`, the instructions file other tools read) are not words.
WORDS = re.compile(r"(?<![\w.-])(agents?|conversations?)(?![\w-]|\.\w)", re.IGNORECASE)

# `label="..."`, `title={'...'}`, `aria-label={`...`}`: a literal given to a text attribute, and the
# same names as object properties (`{ label: 'Agent' }`: a section list, an option, a toast). A
# template literal's `${...}` holes are left out; the words are matched in the text around them.
_ATTR = re.compile(
    r"""(?<![\w-])(?:label|title|aria-label|placeholder|heading)\s*=\s*"""
    r"""(?:"([^"\n]*)"|'([^'\n]*)'|\{\s*(?:"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`)\s*\})"""
    r"""|(?<![\w-])(?:label|title|placeholder|heading|group|ariaLabel)\s*:\s*"""
    r"""(?:"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`)"""
)
# Text between a tag's closing `>` and the next `<` or `{`, with no code in it.
_TEXT = re.compile(r">([^<>{}]*)(?=<|\{)")
# JSX text that follows an expression (`{name} has no thread yet.`): after a `}`, up to the next
# `<` or `{`, holding none of what code between braces holds (quotes, paths, brackets, imports).
_AFTER_EXPRESSION = re.compile(r"\}([^<>{}]*)(?=<|\{)")
_NOT_TEXT = re.compile(
    r"""[()\[\]"`/]|(?<![A-Za-z])'|\b(?:import|from|case|else|type)\b|=>|:\s*$|\w\??:"""
)
# What text holding one of these is: code a `>` happened to precede (a generic, a ternary).
_CODE = re.compile(r"[;=]|\b(?:const|return|if|let|function)\b|&&|\|\||\)\s*[?:]|[?:]\s*\(|^\s*\)")
# Any other prose literal: a string of two words or more where code puts a value (after `(`, `=`,
# `:`, `?`, `,`, `[`, `{`, `+`, `||`, `??` or `return`), which is how a description, a notice, a
# toast or a fallback message reaches the screen. Text in JSX has a letter before its apostrophes,
# so an apostrophe there does not open a literal.
_PROSE = re.compile(
    r"""(?:(?<=[(=:?,\[{+|])|(?<=\breturn)|^)\s*"""
    r"""(?:'([^'\n]*\s[^'\n]*)'|"([^"\n]*\s[^"\n]*)"|`([^`]*\s[^`]*)`)""",
    re.MULTILINE,
)
# A literal compared with, or searched for in, what the Hub sent is data, not text.
_MATCHED = re.compile(
    r"""(?:\.(?:includes|startsWith|endsWith|match|test|indexOf)\(|[!=]==\s*|new RegExp\(|"""
    r"""console\.\w+\(|\bimport\b|\bfrom\s*)\s*$"""
)


class Use(NamedTuple):
    path: str
    line: int
    text: str
    #: Where the text is in the file, as offsets: what a rewording replaces.
    start: int = 0
    end: int = 0


def _strip_comments(source: str) -> str:
    """Blank out `//` and `/* */` comments, keeping offsets (and so line numbers) intact."""

    def blank(match: re.Match) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    source = re.sub(r"/\*.*?\*/", blank, source, flags=re.DOTALL)
    source = re.sub(r"{/\*.*?\*/}", blank, source, flags=re.DOTALL)
    return re.sub(r"(?<![:\"'`\\])//[^\n]*", blank, source)


def _template_text(text: str) -> str:
    return re.sub(r"\$\{[^}]*\}", " ", text)


def _uses_in(rel: str, source: str) -> Iterator[Use]:
    source = _strip_comments(source)
    for match in _ATTR.finditer(source):
        text = next(group for group in match.groups() if group is not None)
        if WORDS.search(_template_text(text)):
            yield Use(
                rel,
                source.count("\n", 0, match.start()) + 1,
                " ".join(text.split()),
                match.start(match.lastindex or 0),
                match.end(match.lastindex or 0),
            )
    for match in _TEXT.finditer(source):
        text = match.group(1)
        if not WORDS.search(text):
            continue
        # The `>` must close a JSX tag, not be an arrow or a comparison.
        if not _closes_tag(source, match.start()) or _CODE.search(text):
            continue
        offset = match.start(1) + len(text) - len(text.lstrip())
        yield Use(
            rel,
            source.count("\n", 0, offset) + 1,
            " ".join(text.split()),
            match.start(1),
            match.end(1),
        )
    for match in _AFTER_EXPRESSION.finditer(source):
        text = match.group(1)
        if WORDS.search(text) and not _CODE.search(text) and not _NOT_TEXT.search(text):
            offset = match.start(1) + len(text) - len(text.lstrip())
            yield Use(
                rel,
                source.count("\n", 0, offset) + 1,
                " ".join(text.split()),
                match.start(1),
                match.end(1),
            )
    yield from _prose_uses(rel, source, 0, source)


def _prose_uses(rel: str, source: str, base: int, whole: str) -> Iterator[Use]:
    """Prose literals in *source* (at *base* in *whole*), and those nested in a template's holes."""
    for match in _PROSE.finditer(source):
        group = next(i for i in (1, 2, 3) if match.group(i) is not None)
        start, text = match.start(group), match.group(group)
        if group == 3 and "${" in text:
            # `${cond ? 'which is archived' : 'which is not an agent'}`: literals inside a hole.
            yield from _prose_uses(rel, text, base + start, whole)
        line_start = source.rfind("\n", 0, start) + 1
        if not WORDS.search(_template_text(text)) or _MATCHED.search(
            source[line_start : start - 1]
        ):
            continue
        if text.startswith("/"):  # a route the app calls: `/api/v1/projects/${id}/agents`
            continue
        yield Use(
            rel,
            whole.count("\n", 0, base + start) + 1,
            " ".join(text.split()),
            base + start,
            base + start + len(text),
        )


def _deduplicated(found: Iterator[Use]) -> Iterator[Use]:
    """One use per line and text: a `label="..."` literal is also a prose literal."""
    seen = set()
    for use in found:
        if (use.line, use.text) not in seen:
            seen.add((use.line, use.text))
            yield use


def _closes_tag(source: str, gt: int) -> bool:
    """Whether the `>` at *gt* ends a JSX opening or closing tag."""
    if gt > 0 and source[gt - 1] in "=-":
        return False
    depth = 0
    for i in range(gt - 1, max(-1, gt - 4000), -1):
        ch = source[i]
        if ch in "}":
            depth += 1
        elif ch == "{":
            depth -= 1
        elif ch == ">" and depth == 0:
            return False
        elif ch == "<" and depth == 0:
            following = source[i + 1 : i + 2]
            return following == "/" or following == ">" or following.isalpha()
    return False


def scanned_files(root: Path = UI_SRC) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.ts*")
        if path.suffix in {".ts", ".tsx"}
        if "__tests__" not in path.parts
        and ".test." not in path.name
        and "fixtures" not in path.parts
    )


def uses(root: Path = UI_SRC) -> list[Use]:
    found = []
    for path in scanned_files(root):
        rel = "hub/ui/src/" + path.relative_to(root).as_posix()
        found.extend(_deduplicated(_uses_in(rel, path.read_text(encoding="utf-8"))))
    return found


def allowlist(path: Path = ALLOWLIST) -> set[tuple[str, str]]:
    allowed: set[tuple[str, str]] = set()
    if not path.exists():
        return allowed
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].strip() if not raw.lstrip().startswith("#") else ""
        if not line:
            continue
        rel, _, text = line.partition(": ")
        allowed.add((rel.strip(), text.strip()))
    return allowed


def problems(root: Path = UI_SRC, allowed_path: Path = ALLOWLIST) -> list[str]:
    allowed = allowlist(allowed_path)
    found = uses(root)
    out = [f"{u.path}:{u.line}: {u.text}" for u in found if (u.path, u.text) not in allowed]
    present = {(u.path, u.text) for u in found}
    out.extend(
        f"{rel}: allowlisted text no longer found, delete its line: {text}"
        for rel, text in sorted(allowed - present)
    )
    settings = root / PROFILE_SETTINGS
    source = settings.read_text(encoding="utf-8") if settings.exists() else ""
    if not re.search(rf"""\bprofiles: ["']{PROFILE_SETTINGS_TITLE}["']""", source):
        out.append(
            f"hub/ui/src/{PROFILE_SETTINGS}: the profile settings' tab is not titled {PROFILE_SETTINGS_TITLE}"
        )
    return out


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for use in uses():
            print(f"{use.path}:{use.line}: {use.text}")
        return 0
    found = problems()
    for problem in found:
        print(problem)
    if found:
        print(f"ui vocabulary: {len(found)} problem(s); say profile, thread or run (FR-10)")
        return 1
    print("ui vocabulary: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
