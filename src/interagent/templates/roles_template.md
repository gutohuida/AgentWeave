# Agent Roles — {project_name}

This file defines the software development role for each AI agent in this session.
Edit it freely, or ask any agent to update it based on your project's needs.

**Session:** {session_id}
**Mode:** {mode}
**Principal:** {principal}

---

## Roles

| Agent | Role | Responsibilities |
|-------|------|-----------------|
{role_rows}

---

## Role Descriptions

| Role | Description |
|------|-------------|
| **Tech Lead** | Owns architecture decisions, reviews all code, resolves conflicts between agents. Drives the overall direction. |
| **Architect** | Designs system structure, data models, and API contracts. Produces specs for other agents to implement. |
| **Backend Developer** | Implements server-side logic, APIs, databases, and business rules. |
| **Frontend Developer** | Implements UI components, styling, client-side state, and browser interactions. |
| **Full Stack Developer** | Works across both backend and frontend — ideal when the team is small. |
| **QA / Test Engineer** | Writes tests (unit, integration, e2e), reviews for edge cases, ensures quality gates. |
| **DevOps Engineer** | Manages CI/CD pipelines, infrastructure, Docker/Kubernetes, deployment scripts. |
| **Security Engineer** | Reviews for vulnerabilities, implements auth/authz, audits dependencies. |
| **Data Engineer** | Designs data pipelines, ETL processes, analytics, and data storage. |
| **ML / AI Engineer** | Implements machine learning models, training pipelines, and inference services. |
| **Technical Writer** | Writes documentation, READMEs, API docs, and user guides. |
| **Code Reviewer** | Reviews pull requests, enforces style guides, and catches logic errors. |
| **Project Manager** | Tracks progress, updates task statuses, and coordinates between agents. |

---

## How Agents Use This File

1. **On session start** — each agent reads this file to understand its scope.
2. **Before creating a task** — check which agent owns the relevant domain.
3. **When in doubt** — the principal ({principal}) makes the final call on role boundaries.
4. **To update** — ask any agent: "Update ROLES.md: assign gemini the Frontend Developer role."

---

## Modifying Roles

To change a role, either:
- Edit this file directly, or
- Ask an agent: *"Update ROLES.md: change kimi's role to Full Stack Developer"*
- Or ask for a research-based recommendation:
  *"Based on our stack (Node.js API, React frontend, PostgreSQL), recommend roles for [agents]"*

Available roles: `tech_lead`, `architect`, `backend_dev`, `frontend_dev`, `fullstack_dev`,
`qa_engineer`, `devops_engineer`, `security_engineer`, `data_engineer`, `ml_engineer`,
`technical_writer`, `code_reviewer`, `project_manager`
