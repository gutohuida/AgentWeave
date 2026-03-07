# Template Update Task

**Date:** {date}
**Assigned to:** {agent}
**Focus:** {focus}

## Your Task

You are responsible for keeping the project kickoff template current with the
latest AI coding best practices and tool capabilities.

## Steps

### 1. Research (search the web)

Search for the following topics - focus on {year}:

- "Claude Code sub-agents best practices {year}"
- "Kimi Code agents capabilities {year}"
- "AI coding workflow multi-agent patterns {year}"
- "Claude Code hooks slash commands new features {year}"
- Recent Anthropic developer blog posts about Claude Code
- Recent Moonshot AI / Kimi developer docs about Kimi Code agents

### 2. Review the Current Template

Read the file at: `{template_path}`

Pay attention to:
- Any commands that reference specific versions or flags
- Steps that describe Claude Code or Kimi Code behavior
- The cross-agent sub-agent prompting section
- The InterAgent CLI commands mentioned

### 3. Identify Improvements

Look for:
- New sub-agent or tool capabilities in Claude Code or Kimi Code
- Outdated commands, flags, or workflows
- Better multi-agent collaboration patterns
- Improved prompt structures
- New `interagent` CLI commands that should be documented
- New cross-agent prompting techniques discovered since the last update

### 4. Update the Template

Edit the file at `{template_path}` with your improvements.
Rules:
- Make targeted, minimal changes - do not restructure working sections
- Update version years (e.g. "2025/2026") if appropriate
- Add new capabilities where relevant
- Remove references to features that no longer exist

### 5. Write Change Summary

Create (or overwrite) `TEMPLATE_UPDATE.md` in the same directory as the
template with:
- Date of update
- List of changes made and the reason for each
- Sources and links you referenced
- Any open questions or areas that need the user's decision

## Focus Area for This Run

{focus}

## Expected Output

1. Updated `{template_path}`
2. New `TEMPLATE_UPDATE.md` in the same directory as the template
