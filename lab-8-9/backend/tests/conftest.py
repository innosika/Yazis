from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Iterator
from typing import Any

import pytest

# Must happen before anything imports app.config: settings are read once.
os.environ["FAKE_ENGINES"] = "1"
os.environ["GROQ_API_KEY"] = ""
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="lector-test-")


@pytest.fixture(scope="session")
def client() -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        for _ in range(200):
            if c.get("/api/health/ready").status_code == 200:
                break
            time.sleep(0.05)
        yield c
