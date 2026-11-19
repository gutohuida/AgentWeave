"""Put an entry in a profile's pool from a test (`a-profile-runs-each-task-on-a-runner-and-model-
chosen-from-its-pool`).

A chat may choose only what its profile's pool holds (FR-9), so a test that sends a model or an
effort override first puts that entry in the pool, through the agents API the settings page uses.
"""

from typing import Optional

PROJECT_BASE = "/api/v1/projects/proj-test"


async def add_pool_entry(
    app,
    auth_headers,
    agent_name: str,
    *,
    effort: Optional[str] = None,
    cli: Optional[str] = None,
    model: Optional[str] = None,
    flags: Optional[list] = None,
) -> str:
    """Add an entry to *agent_name*'s pool and return its runner's id.

    On a new runner of *cli*, *model* and *flags* when any is given, else on the agent's default
    runner, with *effort*. The default entry stays the default.
    """
    listed = await app.get(f"{PROJECT_BASE}/agents", headers=auth_headers)
    agent = next(a for a in listed.json() if a["name"] == agent_name)
    pool = [
        {"runner_id": e["runner_id"], "effort": e["effort"], "default": e["default"]}
        for e in agent["pool"]
    ]
    runner_id = agent["runner_id"]
    if cli is not None or model is not None or flags is not None:
        payload: dict = {"name": f"{agent_name}-{model or cli}-{len(pool)}", "cli": cli or "claude"}
        if model:
            payload["model"] = model
        if flags is not None:
            payload["flags"] = flags
        created = await app.post(f"{PROJECT_BASE}/runners", json=payload, headers=auth_headers)
        assert created.status_code == 201, created.text
        runner_id = created.json()["id"]
    pool.append({"runner_id": runner_id, "effort": effort, "default": False})
    patched = await app.patch(
        f"{PROJECT_BASE}/agents/{agent_name}", json={"pool": pool}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    return runner_id
