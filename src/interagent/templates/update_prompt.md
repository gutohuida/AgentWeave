# Template Update Task

**Date:** {date}
**Assigned to:** {agent}
**Focus:** {focus}

## Your Task

Research the latest capabilities and best practices for AI coding agents,
then update the project kickoff template to reflect current tools and workflows.

## Steps

### 1. Research (search the web)

Search for these topics — use today's date ({date}) to focus on the most
recent information:

- "{agent} new features capabilities {year}"
- "{agent} sub-agents tools configuration best practices"
- "AI coding agent multi-agent collaboration {year}"
- "AI coding workflow best practices {year}"
- "multi-agent software development patterns {year}"
- Recent official docs or developer blog posts from the provider of {agent}
- New AI coding tools or agents released recently

Also reflect on your own built-in knowledge: what capabilities or commands do
you have that may not yet appear in the template?

### 2. Review the Current Template

Read the file at: `{template_path}`

Pay attention to:
- Commands or flags that reference specific versions or may be outdated
- Steps describing AI agent behavior that may have changed
- The multi-agent collaboration sections
- The InterAgent CLI commands referenced
- Any tool-specific language that should be generalized or updated

### 3. Identify Improvements

Look for opportunities to:
- Document new capabilities of {agent} (and other common AI coding agents)
- Remove or update outdated commands, flags, or workflows
- Improve multi-agent collaboration patterns
- Reflect new `interagent` CLI commands if applicable
- Update cross-agent prompting techniques based on current best practices

### 4. Update the Template

Edit the file at `{template_path}` with your improvements.
Rules:
- Make targeted, minimal changes — do not restructure working sections
- Keep language agent-agnostic where possible (others besides {agent} use this template)
- Add new capabilities where relevant; remove features that no longer exist
- Do not hardcode years — prefer "latest" or relative language

### 5. Write Change Summary

Create (or overwrite) `TEMPLATE_UPDATE.md` in the same directory as the template with:
- Date of update ({date})
- What changed and why
- Sources and links referenced
- Open questions or areas needing the user's decision

## Focus Area for This Run

{focus}

## Expected Output

1. Updated `{template_path}`
2. `TEMPLATE_UPDATE.md` in the same directory as the template
