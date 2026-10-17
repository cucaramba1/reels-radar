import pytest
from reels_radar.db import DB


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")
