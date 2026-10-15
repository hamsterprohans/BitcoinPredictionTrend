import pytest
from app import config


@pytest.fixture(scope="session")
def fixture_dir():
    return config.ARTIFACTS
