"""Кроссплатформенные места: логика выбора ветки; Windows-бэкенды (Whisper, OCR) проверяются на самой Windows."""
import subprocess
from types import SimpleNamespace

from reels_radar import cli, fetch
from reels_radar.config import load_settings, load_themes


def _root(tmp_path, extra=""):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(
        "data_dir: data\nreels_tools: ~/rt\nreels_pipeline: ~/rp\nclaude_bin: ~/bin/claude\nwhisper_bin: ~/w\n"
        "whisper_model: m\nselect_threshold: 10\nmax_frames: 6\nbatch_size: 20\nmin_free_gb: 3\nclaude_timeout: 300\n"
        "keywords: [a]\n" + extra)
    (tmp_path / "config" / "themes.yaml").write_text('vaults:\n  dosug: "~/Obsidian Досуг"\nthemes:\n  X: {folder: f, vault: dosug}\n')
    return tmp_path


def test_paths_expand_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.delenv("WHISPER_BIN", raising=False); monkeypatch.delenv("OCR_BIN", raising=False)
    s = load_settings(_root(tmp_path))
    assert str(s.reels_tools) == str(tmp_path / "h" / "rt")
    assert s.claude_bin == str(tmp_path / "h" / "bin" / "claude")
    assert s.ocr_bin is None
    assert load_themes(tmp_path)["X"].vault == str(tmp_path / "h" / "Obsidian Досуг")


def test_env_overrides_binaries(tmp_path, monkeypatch):
    monkeypatch.setenv("WHISPER_BIN", "/x/whisper_cli"); monkeypatch.setenv("WHISPER_MODEL", "turbo")
    monkeypatch.setenv("OCR_BIN", "/x/ocr"); monkeypatch.setenv("CLAUDE_BIN", "/x/claude")
    s = load_settings(_root(tmp_path))
    assert (s.whisper_bin, s.whisper_model, s.claude_bin, str(s.ocr_bin)) == ("/x/whisper_cli", "turbo", "/x/claude", "/x/ocr")


def test_kill_tree_windows_uses_taskkill(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch.sys, "platform", "win32")
    monkeypatch.setattr(fetch.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    fetch._kill_tree(SimpleNamespace(pid=42))
    assert calls == [["taskkill", "/F", "/T", "/PID", "42"]]


def test_kill_tree_posix_uses_killpg(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch.sys, "platform", "linux")
    monkeypatch.setattr(fetch.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    fetch._kill_tree(SimpleNamespace(pid=42))
    assert calls and calls[0][0] == 42


def test_run_is_active_ignores_self(monkeypatch):
    def procs(cmds):
        return lambda attrs: [SimpleNamespace(pid=pid, info={"cmdline": c}) for pid, c in cmds]
    me = cli.os.getpid()
    monkeypatch.setattr("psutil.process_iter", procs([(me, ["py", "-m", "reels_radar", "run"])]))
    assert cli._run_is_active() is False
    monkeypatch.setattr("psutil.process_iter", procs([(me + 1, ["py", "-m", "reels_radar", "run", "--limit", "60"])]))
    assert cli._run_is_active() is True
    monkeypatch.setattr("psutil.process_iter", procs([(me + 1, ["py", "-m", "reels_radar", "bot"]), (me + 2, None)]))
    assert cli._run_is_active() is False
