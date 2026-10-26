"""The published Hub image starts on its own (`docker run`), not only under docker-compose.

Since `a-hub-that-was-not-told-which-database-refuses-to-open-one` (2026-09-22) a Hub whose process
carries no DATABASE_URL refuses to start rather than guess. `docker-compose.yml` sets one; the
Dockerfile did not, so a bare `docker run` of the image published on every push to master died at
import with `HubNotToldWhichDatabase`. Found preparing the 2.0.0 release (2026-10-26).
"""

from __future__ import annotations

import re
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]


def _final_stage(dockerfile: str) -> str:
    return re.split(r"(?m)^FROM\s", dockerfile)[-1]


def test_the_image_sets_a_database_url_inside_its_data_directory():
    stage = _final_stage((HUB / "Dockerfile").read_text(encoding="utf-8"))
    match = re.search(r"(?m)^ENV\s+DATABASE_URL=(\S+)", stage)
    assert match, "the runtime stage sets no DATABASE_URL: `docker run` refuses to start"
    url = match.group(1)
    assert url.startswith("sqlite+aiosqlite:////app/data/"), url
    assert re.search(r"(?m)^RUN mkdir -p /app/data", stage), "the directory it names must exist"


def test_compose_and_the_image_name_the_same_file():
    stage = _final_stage((HUB / "Dockerfile").read_text(encoding="utf-8"))
    image_url = re.search(r"(?m)^ENV\s+DATABASE_URL=(\S+)", stage)
    compose = (HUB / "docker-compose.yml").read_text(encoding="utf-8")
    compose_url = re.search(r"DATABASE_URL=(\S+)", compose)
    assert image_url and compose_url
    # Compose's relative form resolves against WORKDIR /app; the image's is absolute.
    assert compose_url.group(1).replace(":///data/", ":////app/data/") == image_url.group(1)
