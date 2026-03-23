"""Interactive prompt utilities for the AgentWeave setup wizard."""

import os
import sys
import termios
import tty
from typing import List, Optional, Tuple

from .constants import KNOWN_AGENTS


# ANSI escape codes
class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    REVERSE = "\033[7m"
    HIDDEN = "\033[8m"
    STRIKETHROUGH = "\033[9m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    # Cursor control
    CURSOR_UP = "\033[1A"
    CURSOR_DOWN = "\033[1B"
    CURSOR_RIGHT = "\033[1C"
    CURSOR_LEFT = "\033[1D"
    CURSOR_HOME = "\033[H"
    CLEAR_LINE = "\033[2K"
    CLEAR_SCREEN = "\033[2J"
    SAVE_CURSOR = "\033[s"
    RESTORE_CURSOR = "\033[u"


class Emojis:
    """Emoji constants for visual appeal."""

    WAND = "🪄"
    ROBOT = "🤖"
    CROWN = "👑"
    GLOBE = "🌐"
    PLUG = "🔌"
    ROCKET = "🚀"
    CHECK = "✓"
    CHECK_BOX = "☑"
    CROSS = "✗"
    ARROW = "→"
    ARROW_RIGHT = "▶"
    ARROW_DOWN = "▼"
    FOLDER = "📁"
    SPARKLES = "✨"
    THREAD = "🧵"
    GEAR = "⚙️"
    DOCKER = "🐳"
    KEY = "🔑"
    CHART = "📊"
    INFO = "ℹ️"
    WARNING = "⚠️"
    ERROR = "❌"
    SUCCESS = "✅"
    POINTER = "❯"
    BULLET = "•"
    STAR = "★"
    HEART = "♥"
    DIAMOND = "◆"


def supports_color() -> bool:
    """Check if the terminal supports ANSI colors."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if not sys.stdout.isatty():
        return False
    term = os.environ.get("TERM", "")
    if term in ("dumb", ""):
        return False
    if sys.platform == "win32":
        return os.environ.get("WT_SESSION") is not None or os.environ.get("COLORTERM") in (
            "truecolor",
            "24bit",
        )
    return True


class Styled:
    """Styled text with automatic color detection."""

    _enabled = None

    @classmethod
    def enabled(cls) -> bool:
        if cls._enabled is None:
            cls._enabled = supports_color()
        return cls._enabled

    @classmethod
    def _apply(cls, text: str, *codes: str) -> str:
        if not cls.enabled():
            return text
        return "".join(codes) + text + Colors.RESET

    @classmethod
    def bold(cls, text: str) -> str:
        return cls._apply(text, Colors.BOLD)

    @classmethod
    def dim(cls, text: str) -> str:
        return cls._apply(text, Colors.DIM)

    @classmethod
    def italic(cls, text: str) -> str:
        return cls._apply(text, Colors.ITALIC)

    @classmethod
    def underline(cls, text: str) -> str:
        return cls._apply(text, Colors.UNDERLINE)

    @classmethod
    def red(cls, text: str) -> str:
        return cls._apply(text, Colors.RED)

    @classmethod
    def green(cls, text: str) -> str:
        return cls._apply(text, Colors.GREEN)

    @classmethod
    def yellow(cls, text: str) -> str:
        return cls._apply(text, Colors.YELLOW)

    @classmethod
    def blue(cls, text: str) -> str:
        return cls._apply(text, Colors.BLUE)

    @classmethod
    def cyan(cls, text: str) -> str:
        return cls._apply(text, Colors.CYAN)

    @classmethod
    def magenta(cls, text: str) -> str:
        return cls._apply(text, Colors.MAGENTA)

    @classmethod
    def bright_cyan(cls, text: str) -> str:
        return cls._apply(text, Colors.BRIGHT_CYAN)

    @classmethod
    def bright_green(cls, text: str) -> str:
        return cls._apply(text, Colors.BRIGHT_GREEN)

    @classmethod
    def bright_yellow(cls, text: str) -> str:
        return cls._apply(text, Colors.BRIGHT_YELLOW)

    @classmethod
    def on_green(cls, text: str) -> str:
        return cls._apply(text, Colors.BG_GREEN, Colors.BOLD)

    @classmethod
    def on_cyan(cls, text: str) -> str:
        return cls._apply(text, Colors.BG_CYAN, Colors.BOLD)


def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("cls" if sys.platform == "win32" else "clear")


def move_cursor_up(n: int = 1) -> None:
    """Move cursor up n lines."""
    if Styled.enabled():
        print(f"\033[{n}A", end="")


def move_cursor_down(n: int = 1) -> None:
    """Move cursor down n lines."""
    if Styled.enabled():
        print(f"\033[{n}B", end="")


def clear_line() -> None:
    """Clear the current line."""
    if Styled.enabled():
        print(Colors.CLEAR_LINE, end="")


def get_key() -> str:
    """Read a single keypress from stdin (cross-platform)."""
    if sys.platform == "win32":
        import msvcrt

        key = msvcrt.getch().decode("utf-8", errors="ignore")
        if key == "\x00" or key == "\xe0":
            key = msvcrt.getch().decode("utf-8", errors="ignore")
            arrow_map = {"H": "up", "P": "down", "K": "left", "M": "right"}
            return arrow_map.get(key, key)
        return key
    else:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    arrow_map = {"A": "up", "B": "down", "C": "right", "D": "left"}
                    return arrow_map.get(ch3, ch3)
                return ch2
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def print_banner() -> None:
    """Print the AgentWeave welcome banner."""
    if Styled.enabled():
        print()
        print(
            f"  {Styled.bright_cyan('╔══════════════════════════════════════════════════════════╗')}"
        )
        print(
            f"  {Styled.bright_cyan('║')}  {Emojis.THREAD}  {Styled.bold(Styled.bright_cyan('AgentWeave Setup Wizard'))}                           {Styled.bright_cyan('║')}"
        )
        print(
            f"  {Styled.bright_cyan('║')}                                                          {Styled.bright_cyan('║')}"
        )
        print(
            f"  {Styled.bright_cyan('║')}  {Styled.dim('Set up your multi-agent AI collaboration environment')}    {Styled.bright_cyan('║')}"
        )
        print(
            f"  {Styled.bright_cyan('╚══════════════════════════════════════════════════════════╝')}"
        )
        print()
    else:
        print()
        print("╔══════════════════════════════════════════════════════════╗")
        print("║  AgentWeave Setup Wizard                                 ║")
        print("║  Set up your multi-agent AI collaboration environment    ║")
        print("╚══════════════════════════════════════════════════════════╝")
        print()


def print_step(step_num: int, total_steps: int, emoji: str, title: str) -> None:
    """Print a step header."""
    if Styled.enabled():
        progress = f"{step_num}/{total_steps}"
        bar_width = 20
        filled = int((step_num / total_steps) * bar_width)
        bar = Styled.green("█" * filled) + Styled.dim("░" * (bar_width - filled))
        print(f"\n  {bar} {Styled.bold(progress)}")
        print(f"  {emoji}  {Styled.bold(Styled.bright_cyan(title))}")
        print(f"  {Styled.dim('─' * 50)}")
    else:
        print(f"\n[{step_num}/{total_steps}] {emoji} {title}")
        print("-" * 50)


def print_success_item(message: str) -> None:
    """Print a success item with checkmark."""
    if Styled.enabled():
        print(f"  {Styled.green(Emojis.CHECK)} {message}")
    else:
        print(f"  [OK] {message}")


def print_error_item(message: str) -> None:
    """Print an error item with X."""
    if Styled.enabled():
        print(f"  {Styled.red(Emojis.CROSS)} {message}")
    else:
        print(f"  [ERR] {message}")


def print_info_item(message: str) -> None:
    """Print an info item."""
    if Styled.enabled():
        print(f"  {Styled.dim(Emojis.ARROW)} {message}")
    else:
        print(f"  -> {message}")


def print_selected(message: str) -> None:
    """Print a selected/highlighted item."""
    if Styled.enabled():
        print(f"  {Styled.green(Emojis.POINTER)} {Styled.bright_green(message)}")
    else:
        print(f"  > {message}")


def ask_text(
    prompt: str,
    default: Optional[str] = None,
    required: bool = False,
    validator: Optional[callable] = None,
) -> str:
    """Ask for text input with optional default and validation."""
    while True:
        full_prompt = f"{prompt} [{default}]: " if default is not None else f"{prompt}: "

        if Styled.enabled():
            print(f"  {Styled.cyan(Emojis.POINTER)}", end=" ")
        else:
            print("> ", end="")

        try:
            user_input = input(full_prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print("\nSetup cancelled.")
            sys.exit(1)

        if not user_input and default is not None:
            user_input = default

        if required and not user_input:
            if Styled.enabled():
                print(f"  {Styled.red(Emojis.ERROR)} {Styled.red('This field is required.')}")
            else:
                print("  [ERR] This field is required.")
            continue

        if validator and user_input:
            is_valid, error_msg = validator(user_input)
            if not is_valid:
                if Styled.enabled():
                    print(
                        f"  {Styled.red(Emojis.ERROR)} {Styled.red(error_msg or 'Invalid input.')}"
                    )
                else:
                    print(f"  [ERR] {error_msg or 'Invalid input.'}")
                continue

        return user_input


def ask_confirm(prompt: str, default: bool = True) -> bool:
    """Ask for yes/no confirmation."""
    default_str = "Y/n" if default else "y/N"

    while True:
        if Styled.enabled():
            print(f"  {Styled.cyan(Emojis.POINTER)}", end=" ")
        else:
            print("> ", end="")

        full_prompt = f"{prompt} [{default_str}]: "
        try:
            user_input = input(full_prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            print("\nSetup cancelled.")
            sys.exit(1)

        if not user_input:
            return default

        if user_input in ("y", "yes"):
            return True
        if user_input in ("n", "no"):
            return False

        if Styled.enabled():
            print(f"  {Styled.yellow(Emojis.WARNING)} {Styled.yellow('Please enter y or n.')}")
        else:
            print("  [WARN] Please enter y or n.")


def ask_choice(
    prompt: str,
    choices: List[Tuple[str, str]],
    default: Optional[str] = None,
) -> str:
    """Ask user to select from a list using arrow key navigation."""
    print()
    if Styled.enabled():
        print(f"  {Styled.dim(prompt)}")
    else:
        print(prompt)

    # Find default index
    current_idx = 0
    for i, (value, _) in enumerate(choices):
        if value == default:
            current_idx = i
            break

    # Selection loop
    while True:
        # Redraw all options
        for i, (_value, desc) in enumerate(choices):
            is_selected = i == current_idx

            if Styled.enabled():
                if is_selected:
                    prefix = Styled.green(Emojis.POINTER)
                    text = Styled.on_cyan(f" {desc} ")
                else:
                    prefix = " "
                    text = f" {desc}"
                print(f"    {prefix} {text}")
            else:
                prefix = ">" if is_selected else " "
                print(f"    [{prefix}] {desc}")

        # Get key input
        print(
            f"\n  {Styled.dim('Use ↑↓ arrows, Enter to select')}"
            if Styled.enabled()
            else "\n  (Use arrow keys, Enter to select)"
        )

        key = get_key()

        # Clear previous lines for redraw
        if Styled.enabled():
            for _ in range(len(choices) + 2):
                move_cursor_up()
                clear_line()

        if key == "up":
            current_idx = (current_idx - 1) % len(choices)
        elif key == "down":
            current_idx = (current_idx + 1) % len(choices)
        elif key == "\r" or key == "\n":
            # Selection made
            if Styled.enabled():
                move_cursor_down(len(choices) + 2)
            print()
            return choices[current_idx][0]
        elif key == "\x03":
            print("\nSetup cancelled.")
            sys.exit(1)


def ask_agents() -> List[str]:
    """Ask user to select multiple agents with interactive checkboxes."""
    print()
    if Styled.enabled():
        print(f"  {Styled.bold(Styled.bright_cyan('Select AI agents to collaborate:'))}")
        print(f"  {Styled.dim('Space to toggle, ↑↓ to navigate, Enter to confirm')}")
    else:
        print("Select AI agents to collaborate:")
        print("Space to toggle, arrows to navigate, Enter to confirm")
    print()

    # Agent descriptions
    descriptions = {
        "claude": "Claude Code (Anthropic)     - Code, review, architecture",
        "kimi": "Kimi Code (Moonshot AI)     - Fast, context-aware coding",
        "gemini": "Gemini CLI (Google)         - 1M context, reasoning",
        "codex": "Codex CLI (OpenAI)          - GPT-4 powered coding",
        "aider": "Aider                       - Git-native pair programmer",
        "cline": "Cline                       - MCP-based VS Code agent",
        "cursor": "Cursor Agent (Anysphere)    - Full IDE integration",
        "windsurf": "Windsurf / Cascade          - Codeium's agent mode",
        "copilot": "GitHub Copilot Agent        - Microsoft's AI assistant",
        "opendevin": "OpenHands / OpenDevin       - Open autonomous agent",
        "gpt": "ChatGPT / OpenAI            - General assistant",
        "qwen": "Qwen (Alibaba)              - Multilingual coding",
    }

    # Default selection
    selected = {"claude", "kimi"}
    current_idx = 0
    agents = list(KNOWN_AGENTS)

    while True:
        # Draw all options
        for i, agent in enumerate(agents):
            is_current = i == current_idx
            is_selected = agent in selected
            desc = descriptions.get(agent, agent)

            if Styled.enabled():
                # Checkbox style
                checkbox = Styled.green(f"[{Emojis.CHECK}]") if is_selected else Styled.dim("[ ]")

                if is_current:
                    pointer = Styled.green(Emojis.POINTER)
                    name = Styled.bright_green(agent.capitalize())
                    desc_text = Styled.bold(desc)
                else:
                    pointer = " "
                    name = Styled.bold(agent.capitalize()) if is_selected else agent.capitalize()
                    desc_text = desc if is_selected else Styled.dim(desc)

                print(f"    {pointer} {checkbox} {name:<12} {desc_text}")
            else:
                checkbox = "[X]" if is_selected else "[ ]"
                pointer = ">" if is_current else " "
                print(f"    {pointer} {checkbox} {agent.capitalize():<12} {desc}")

        # Instructions at bottom
        print()
        if Styled.enabled():
            print(f"  {Styled.dim('Space: toggle  ↑↓: navigate  Enter: confirm  Q: quit')}")
        else:
            print("  Space: toggle | ↑↓: navigate | Enter: confirm | Q: quit")

        # Get key
        key = get_key()

        # Clear lines for redraw
        if Styled.enabled():
            for _ in range(len(agents) + 2):
                move_cursor_up()
                clear_line()

        if key == "up":
            current_idx = (current_idx - 1) % len(agents)
        elif key == "down":
            current_idx = (current_idx + 1) % len(agents)
        elif key == " ":
            # Toggle selection
            agent = agents[current_idx]
            if agent in selected:
                selected.remove(agent)
            else:
                selected.add(agent)
        elif key == "\r" or key == "\n":
            # Confirm selection
            if not selected:
                if Styled.enabled():
                    move_cursor_down(len(agents) + 2)
                    print(f"  {Styled.yellow(Emojis.WARNING)} Please select at least one agent")
                    print()
                    for _ in range(3):
                        move_cursor_up()
                else:
                    print("  [WARN] Please select at least one agent")
                continue

            if Styled.enabled():
                move_cursor_down(len(agents) + 2)
            print()
            return list(selected)
        elif key == "q" or key == "Q" or key == "\x03":
            print("\nSetup cancelled.")
            sys.exit(1)


def print_section(title: str) -> None:
    """Print a section divider."""
    print()
    if Styled.enabled():
        print(f"  {Styled.bright_cyan('─' * 52)}")
        print(f"  {Styled.bold(title)}")
        print(f"  {Styled.bright_cyan('─' * 52)}")
    else:
        print("=" * 54)
        print(title)
        print("=" * 54)


def print_summary(
    project_name: str,
    agents: List[str],
    principal: str,
    mode: str,
    hub_configured: bool,
    hub_url: Optional[str],
    mcp_configured: bool,
    watchdog_started: bool,
) -> None:
    """Print the setup summary."""
    print_section(f"{Emojis.SPARKLES} Setup Complete!")
    print()

    if Styled.enabled():
        # Project info box
        print(f"  {Styled.bright_cyan('┌────────────────────────────────────────────────────┐')}")
        print(
            f"  {Styled.bright_cyan('│')}  {Styled.bold('Project:')}  {project_name:<38} {Styled.bright_cyan('│')}"
        )
        print(
            f"  {Styled.bright_cyan('│')}  {Styled.bold('Agents:')}   {', '.join(agents):<38} {Styled.bright_cyan('│')}"
        )
        print(
            f"  {Styled.bright_cyan('│')}  {Styled.bold('Principal:')} {principal:<38} {Styled.bright_cyan('│')}"
        )
        print(
            f"  {Styled.bright_cyan('│')}  {Styled.bold('Mode:')}     {mode:<38} {Styled.bright_cyan('│')}"
        )
        print(f"  {Styled.bright_cyan('└────────────────────────────────────────────────────┘')}")

        if hub_configured and hub_url:
            print()
            print(
                f"  {Styled.green(Emojis.GLOBE)}  Dashboard: {Styled.bright_cyan(Styled.underline(hub_url))}"
            )

        print()
        print(f"  {Styled.bold('Status:')}")
        if hub_configured:
            print(f"    {Styled.green(Emojis.CHECK)} Hub configured")
        if mcp_configured:
            print(f"    {Styled.green(Emojis.CHECK)} MCP server configured")
        if watchdog_started:
            print(f"    {Styled.green(Emojis.CHECK)} Watchdog running")
    else:
        print(f"  Project: {project_name}")
        print(f"  Agents: {', '.join(agents)}")
        print(f"  Principal: {principal}")
        print(f"  Mode: {mode}")

        if hub_configured and hub_url:
            print(f"\n  Dashboard: {hub_url}")

        print("\n  Status:")
        if hub_configured:
            print("    [OK] Hub configured")
        if mcp_configured:
            print("    [OK] MCP server configured")
        if watchdog_started:
            print("    [OK] Watchdog running")

    print()
    print("  Next steps:")
    if Styled.enabled():
        print(
            f"    {Styled.cyan('1.')}" + f" Open the dashboard: {Styled.underline(hub_url)}"
            if hub_url
            else "    1. Set up the Hub: agentweave hub setup"
        )
        print(f"    {Styled.cyan('2.')} Start your agents (they auto-connect via MCP)")
        print(f"    {Styled.cyan('3.')} Create your first task:")
        cmd_example = 'agentweave quick --to kimi "Implement auth"'
        print(f"       {Styled.cyan(cmd_example)}")
    else:
        print("    1. Open the dashboard in your browser")
        print("    2. Start your agents (they'll auto-connect via MCP)")
        print("    3. Create your first task: agentweave quick --to kimi 'Task'")

    print()
