from reels_radar.local import clean_lines, score


def test_clean_lines_dedups_and_drops_noise():
    blocks = ["Hello world\n12:30\nab", "hello   WORLD\nПривет мир"]
    assert clean_lines(blocks) == ["Hello world", "Привет мир"]


def test_score_monotonic_and_capped():
    kw = ["claude"]
    low = score("", "", "", kw)
    mid = score("слово " * 100, "", "", kw)
    assert low == 0 and mid > low
    assert score("слово " * 10000, "текст " * 10000, "claude " * 50, kw) <= 100


def test_keywords_add_points():
    assert score("", "", "claude mcp", ["claude", "mcp"]) > score("", "", "ничего", ["claude", "mcp"])
