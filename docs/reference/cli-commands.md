# CLI commands

The single-runtime CLI manages the local AgentWeave application. Collaboration state is managed in
the dashboard or through the agent capability plane.

## Start or open

```bash
agentweave [--port PORT] [--docker] [--local] [--no-detach]
```

Bare invocation starts the native Hub in app mode by default. If it is already running, AgentWeave
opens that instance.

## Doctor

```bash
agentweave doctor [--json] [--no-network]
```

Reports installation and local readiness without creating Hub state. JSON output uses stable check
IDs and never includes secret values.

## Status

```bash
agentweave status [--port PORT]
```

Reports whether the instance is running, its URL, native PID when applicable, and bootstrap project
identity when available.

## Stop

```bash
agentweave stop [--port PORT] [--local]
```

Stops a confirmed native instance or the configured Docker instance. A stale native PID is never
used to kill an unrelated process.

## Reset

```bash
agentweave reset [--all] [--yes]
```

Deletes local database state after confirmation. `--all` also removes local configuration and log
files. This is destructive.

## Version

```bash
agentweave --version
```
