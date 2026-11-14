"""The operator's shells in the conversation side panel (`a-terminal-in-the-side-panel`, TSP-2).

A shell is command execution on the operator's computer, so who may open one is the package's
central rule (`access`): loopback only, the operator signed in, from the app's own page, and never
in Docker mode. Shells live in the Hub's memory only (`sessions`); a page reload, Restart, close
and Hub stop end them and every process they started. `shells` detects what is installed;
`environment` hands a shell the operator's environment without the Hub's own variables.
"""

from .sessions import LIMIT, MAX_LINES, registry

__all__ = ["LIMIT", "MAX_LINES", "registry"]
