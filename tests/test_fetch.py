from pathlib import Path
from reels_radar.fetch import fetch_chain


def mk(status, make_file=False):
    def f(url, dest: Path):
        if make_file:
            (dest / "v.mp4").write_bytes(b"x")
        return status
    return f


def test_first_ok_wins(tmp_path):
    st, path = fetch_chain("u", tmp_path, [mk("LOGIN"), mk("OK", True), mk("OK", True)])
    assert st == "OK" and path.name == "v.mp4"


def test_rate_stops_chain(tmp_path):
    calls = []
    def spy(url, dest):
        calls.append(1); return "OK"
    st, path = fetch_chain("u", tmp_path, [mk("RATE"), spy])
    assert st == "RATE" and path is None and not calls


def test_all_fail_is_no_video(tmp_path):
    st, path = fetch_chain("u", tmp_path, [mk("LOGIN"), mk("NO_VIDEO")])
    assert st == "NO_VIDEO" and path is None


def test_ok_without_file_continues(tmp_path):
    st, path = fetch_chain("u", tmp_path, [mk("OK", False), mk("OK", True)])
    assert st == "OK" and path is not None


def test_image_only_post_is_ok_with_dir(tmp_path):
    def gdl(url, dest):
        (dest / "1.jpg").write_bytes(b"x"); (dest / "2.jpg").write_bytes(b"x")
        return "OK"
    st, path = fetch_chain("u", tmp_path, [mk("NO_VIDEO"), gdl])
    assert st == "OK" and path == tmp_path
