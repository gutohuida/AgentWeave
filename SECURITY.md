# Security policy

## Supported versions

Security fixes go into the latest release only. Upgrade with `pip install -U agentweave-ai`.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub:
[Report a vulnerability](https://github.com/gutohuida/AgentWeave/security/advisories/new).
Include what an attacker can do, the version affected, and the steps to reproduce it.

You can expect an acknowledgement within 3 days and an assessment within 10. Once a fix is
released, the advisory is published and you are credited unless you ask not to be.

## What is in scope

AgentWeave runs on your own machine and starts AI coding agents that can read and write your
code, so these matter most:

- the Hub accepting requests from anything other than the local operator and the agents it started
- an agent acting outside the permissions its project grants it, or reaching another project
- credentials (Hub keys, run credentials, provider keys) leaking into logs, the app, the knowledge
  vault or git
- the Docker image exposing more of the host than the documented workspace mount

What an agent does with permissions you granted it is the agent CLI's behaviour, not a
vulnerability in AgentWeave, unless AgentWeave granted more than you chose.
