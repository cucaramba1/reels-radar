from pathlib import Path
import pytest
from reels_radar import fetch as fetch_mod
from reels_radar.fetch import fetch_chain

REAL_PROBE = fetch_mod.has_video_stream


@pytest.fixture(autouse=True)
def fake_probe(monkeypatch):
    # заглушки-«видео» в этих тестах это байты b"x"; настоящий ffprobe проверяется отдельно
    monkeypatch.setattr(fetch_mod, "has_video_stream", lambda p: p.read_bytes() == b"x")


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


def test_audio_only_mp4_is_dropped_and_next_fetcher_gives_images(tmp_path):
    import subprocess
    from reels_radar.fetch import fetch_chain

    def audio_only(url, dest):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=1", str(dest / "pw.mp4")], check=True)
        return "OK"

    def photos(url, dest):
        (dest / "a.jpg").write_bytes(b"x")
        return "OK"

    st, res = fetch_chain("u", tmp_path / "w", [audio_only, photos])
    assert st == "OK" and res == tmp_path / "w" and not (tmp_path / "w" / "pw.mp4").exists()
    st, res = fetch_chain("u", tmp_path / "w2", [audio_only])
    assert st == "NO_VIDEO" and res is None


def test_has_video_stream_real_ffprobe(tmp_path):
    import subprocess
    a, v = tmp_path / "a.mp4", tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=1", str(a)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", str(v)], check=True)
    assert REAL_PROBE(v) is True and REAL_PROBE(a) is False
