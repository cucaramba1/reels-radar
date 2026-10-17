from reels_radar.sources.cards import chunk_lines


def test_chunk_lines_respects_limit_and_keeps_order():
    lines = [f"user{i} - причина" for i in range(500)]
    chunks = chunk_lines(lines, limit=200)
    assert all(len(c) <= 200 for c in chunks)
    assert "\n".join(chunks).split("\n") == lines


def test_chunk_lines_empty():
    assert chunk_lines([]) == []
