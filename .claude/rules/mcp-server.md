---
paths:
  - "hub/hub/mcp_server.py"
---

# Hub MCP server rules (loaded when `hub/hub/mcp_server.py` is read)

- `hub/hub/mcp_server.py` is spawned standalone and may import **only** stdlib + fastmcp — anything
  it needs from the Hub is restated there, with a test asserting the two agree.
- `approve_tool_call` has **no return annotation**. FastMCP would derive `structuredContent` from
  one, which silently defeats an `allow`. Do not add one.
- A Hub spawns the copy of this file it pinned at start (`hub/hub/tool_server.py`, under
  `~/.agentweave/hub/tool-server/<digest>/`), so an edit here reaches a Hub's agents on that Hub's
  next restart, not before. `:8000` runs this checkout, so its restart carries the edit.

## Adding an MCP tool

1. Add an `@mcp.tool()` decorated function in `hub/hub/mcp_server.py`.
2. Use existing core modules (within the import restriction above).
3. Follow the existing error-handling patterns.
