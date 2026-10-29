"""The content version an approval names (`approve-what-was-seen`), read as the operator's page reads it.

An approval is refused unless it names the `content_version` of the document read the operator
approved; a test that approves reads the document first, as the page does.
"""


async def content_version(app, headers, path: str, project: str = "proj-test") -> str:
    read = await app.get(
        f"/api/v1/projects/{project}/project/spec", params={"path": path}, headers=headers
    )
    assert read.status_code == 200, read.text
    return read.json()["content_version"]
