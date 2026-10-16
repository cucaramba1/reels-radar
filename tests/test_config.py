from pathlib import Path
from reels_radar.config import load_settings, load_themes

ROOT = Path(__file__).resolve().parent.parent


def test_load_settings_and_themes():
    s = load_settings(ROOT)
    assert s.select_threshold == 10 and s.max_frames == 6
    themes = load_themes(ROOT)
    assert "Съёмка и монтаж" in themes and "Слова и фразы" in themes
    assert themes["ИИ"].folder
