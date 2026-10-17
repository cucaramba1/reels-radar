import pytest
from reels_radar.sources.db import SourcesDB


@pytest.fixture
def sdb(tmp_path):
    return SourcesDB(tmp_path / "s.db")
