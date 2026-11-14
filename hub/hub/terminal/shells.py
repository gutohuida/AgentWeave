"""The shells installed on the Hub's computer, and how each one is started (FR-4, FR-5).

Detected, never configured: the new-shell menu lists what this computer has and only that. On
Windows that is whichever of PowerShell 7, Windows PowerShell, Command Prompt and Git Bash are
found, and every installed WSL distribution (Docker Desktop's own `docker-desktop*` distributions
are its machinery, not shells, and are left out); elsewhere the operator's login shell and the
shells `/etc/shells` lists that exist.

Each shell names its starting directory the way it prints it: a WSL shell as `/mnt/<drive>/...`
(asked of `wslpath`, so a distribution with its own mount root says its own), Git Bash as
`/c/...`, the rest as Windows or POSIX paths.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..subprocess_windows import no_console_kwargs

IS_WINDOWS = sys.platform == "win32"
#: How long one detection is reused: `wsl.exe -l` can take a second, and may start WSL's service.
DETECTION_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class ShellOption:
    """One entry of the new-shell menu."""

    id: str
    label: str
    #: The executable, as the menu's second line shows it.
    detail: str
    argv: Tuple[str, ...]
    kind: str  # "windows" | "git-bash" | "wsl" | "posix"
    distribution: Optional[str] = None
    extra_env: Tuple[Tuple[str, str], ...] = field(default=())

    @property
    def wsl(self) -> bool:
        return self.kind == "wsl"

    def to_dict(self) -> Dict[str, object]:
        return {"id": self.id, "label": self.label, "detail": self.detail, "wsl": self.wsl}


# --------------------------------------------------------------------------- Windows


def _windows_dir() -> Path:
    return Path(os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR") or r"C:\Windows")


def _program_files() -> List[Path]:
    seen: List[Path] = []
    for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        value = os.environ.get(name)
        if value and Path(value) not in seen:
            seen.append(Path(value))
    return seen


def _first_file(candidates) -> Optional[Path]:
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def _git_bash() -> Optional[Path]:
    """`<Git>/bin/bash.exe` of a Git for Windows install: the one git on PATH comes from, else the
    default install. `<Git>/git-bash.exe` beside it is what makes it Git Bash rather than any
    `bash.exe` (WSL's `System32\\bash.exe` is not Git Bash)."""
    roots: List[Path] = []
    git = shutil.which("git")
    if git:
        roots.extend(Path(git).resolve().parents)
    roots.extend(p / "Git" for p in _program_files())
    for root in roots:
        bash = root / "bin" / "bash.exe"
        if bash.is_file() and (root / "git-bash.exe").is_file():
            return bash
    return None


def _decode_wsl(raw: bytes) -> str:
    # wsl.exe writes UTF-16LE to a pipe unless WSL_UTF8=1 is set.
    if b"\x00" in raw:
        return raw.decode("utf-16-le", errors="ignore")
    return raw.decode("utf-8", errors="ignore")


def wsl_distributions() -> List[str]:
    """Installed WSL distributions, default first, as `wsl.exe -l -q` lists them."""
    wsl = _first_file([_windows_dir() / "System32" / "wsl.exe"]) or shutil.which("wsl")
    if not wsl:
        return []
    try:
        done = subprocess.run(
            [str(wsl), "-l", "-q"], capture_output=True, timeout=20, **no_console_kwargs()
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    names = [line.strip().strip("\ufeff") for line in _decode_wsl(done.stdout).splitlines()]
    return [n for n in names if n and not n.lower().startswith("docker-desktop")]


def _wsl_exe() -> str:
    found = _first_file([_windows_dir() / "System32" / "wsl.exe"])
    return str(found) if found else "wsl.exe"


def _windows_options() -> List[ShellOption]:
    options: List[ShellOption] = []
    pwsh = shutil.which("pwsh") or _first_file(
        p / "PowerShell" / "7" / "pwsh.exe" for p in _program_files()
    )
    if pwsh:
        options.append(
            ShellOption("pwsh", "PowerShell 7", str(pwsh), (str(pwsh), "-NoLogo"), "windows")
        )
    powershell = _first_file(
        [_windows_dir() / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"]
    ) or shutil.which("powershell")
    if powershell:
        options.append(
            ShellOption(
                "powershell",
                "Windows PowerShell",
                str(powershell),
                (str(powershell), "-NoLogo"),
                "windows",
            )
        )
    cmd = _first_file([os.environ.get("COMSPEC"), _windows_dir() / "System32" / "cmd.exe"])
    if cmd:
        options.append(ShellOption("cmd", "Command Prompt", str(cmd), (str(cmd),), "windows"))
    bash = _git_bash()
    if bash:
        options.append(
            ShellOption(
                "git-bash",
                "Git Bash",
                str(bash),
                (str(bash), "--login", "-i"),
                "git-bash",
                # A login shell would `cd ~`; CHERE_INVOKING keeps it where it was started.
                extra_env=(("CHERE_INVOKING", "1"), ("MSYSTEM", "MINGW64")),
            )
        )
    wsl = _wsl_exe()
    for distribution in wsl_distributions():
        options.append(
            ShellOption(
                f"wsl:{distribution}",
                f"{distribution} (WSL)",
                f"wsl.exe -d {distribution}",
                (wsl, "-d", distribution),
                "wsl",
                distribution=distribution,
            )
        )
    return options


# --------------------------------------------------------------------------- POSIX


def _posix_options() -> List[ShellOption]:
    candidates: List[str] = []
    login = os.environ.get("SHELL")
    if not login:
        try:
            import pwd

            login = pwd.getpwuid(os.getuid()).pw_shell  # type: ignore[attr-defined]
        except (ImportError, KeyError, OSError):
            login = None
    if login:
        candidates.append(login)
    try:
        for line in Path("/etc/shells").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                candidates.append(line)
    except OSError:
        pass
    options: List[ShellOption] = []
    seen = set()
    for path in candidates:
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            continue
        real = os.path.realpath(path)
        if real in seen or os.path.basename(real) in ("nologin", "false"):
            continue
        seen.add(real)
        name = os.path.basename(path)
        label = f"{name} (login shell)" if path == login else name
        options.append(ShellOption(f"shell:{path}", label, path, (path, "-l"), "posix"))
    return options


# --------------------------------------------------------------------------- detection


_cache_lock = threading.Lock()
_cache: Optional[Tuple[float, List[ShellOption]]] = None


def detect(refresh: bool = False) -> List[ShellOption]:
    """The installed shells, detected at most every `DETECTION_TTL_SECONDS`. Blocking."""
    global _cache
    with _cache_lock:
        if not refresh and _cache is not None and _cache[0] > time.monotonic():
            return list(_cache[1])
        options = _windows_options() if IS_WINDOWS else _posix_options()
        _cache = (time.monotonic() + DETECTION_TTL_SECONDS, options)
        return list(options)


def _reset_detection_cache() -> None:
    """A test seam."""
    global _cache
    with _cache_lock:
        _cache = None


def find(option_id: str) -> Optional[ShellOption]:
    return next((o for o in detect() if o.id == option_id), None)


# --------------------------------------------------------------------------- directories


def _mnt_path(directory: Path) -> str:
    """`C:\\x\\y` -> `/mnt/c/x/y`, WSL's default automount (the fallback when `wslpath` fails)."""
    text = str(directory)
    if len(text) >= 2 and text[1] == ":":
        rest = text[2:].replace("\\", "/")
        return f"/mnt/{text[0].lower()}{rest}"
    return text.replace("\\", "/")


def wsl_directory(distribution: str, directory: Path) -> str:
    """*directory* as the WSL distribution names it, asked of its own `wslpath`. Blocking."""
    try:
        done = subprocess.run(
            [_wsl_exe(), "-d", distribution, "--", "wslpath", "-a", "-u", str(directory)],
            capture_output=True,
            timeout=20,
            **no_console_kwargs(),
        )
        printed = _decode_wsl(done.stdout).strip()
        if done.returncode == 0 and printed.startswith("/"):
            return printed
    except (OSError, subprocess.SubprocessError):
        pass
    return _mnt_path(directory)


def shown_directory(option: ShellOption, directory: Path) -> str:
    """The directory as *option*'s shell prints it. Blocking for a WSL shell."""
    if option.kind == "wsl" and option.distribution:
        return wsl_directory(option.distribution, directory)
    if option.kind == "git-bash":
        text = str(directory)
        if len(text) >= 2 and text[1] == ":":
            return f"/{text[0].lower()}{text[2:].replace(chr(92), '/')}"
        return text.replace("\\", "/")
    return str(directory)


def launch_argv(option: ShellOption, directory: Path) -> List[str]:
    """The command starting *option* in *directory*."""
    if option.kind == "wsl":
        return [*option.argv, "--cd", str(directory)]
    return list(option.argv)
