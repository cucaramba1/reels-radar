import pytest
from reels_radar.db import DB


@pytest.fixture(autouse=True)
def _no_real_yield(tmp_path, monkeypatch):  # живой флаг tools/slot не должен влиять на тесты
    monkeypatch.setenv("SLOT_YIELD", str(tmp_path / "no-yield"))


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")
