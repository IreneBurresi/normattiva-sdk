from pathlib import Path

import pytest

from tests.dati import FIXTURES


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
