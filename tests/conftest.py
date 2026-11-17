import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.line_api import DryRunClient  # noqa: E402
from app.service import Service  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def svc():
    conn = connect(":memory:")
    s = Settings(channel_secret="test-secret", public_url="https://example.test")
    return Service(conn, DryRunClient(), s)
