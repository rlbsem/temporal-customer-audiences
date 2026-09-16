import pytest

from temporal_audiences.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "audiences.sqlite")
