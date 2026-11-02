"""claude -p раннер (скопирован из tg-harvester/harvester/brain.py, логика без изменений)."""
from __future__ import annotations

import asyncio
import json
import re
import os
import sys
from pathlib import Path

from .config import Settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "llm_fallback"))
import llm_fallback  # noqa: E402


class BrainError(RuntimeError):
    pass


async def run_claude(s: Settings, prompt: str, *, system: str, schema: dict | None = None,
                     tools: tuple[str, ...] = (), add_dirs: tuple[str, ...] = (), timeout: int) -> dict | str:
    args = [s.claude_bin, "-p", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--output-format", "json", "--no-session-persistence",
            "--system-prompt", system, "--tools", ",".join(tools)]
    if tools:
        args += ["--allowedTools", ",".join(tools)]  # без этого в -p тул упрётся в запрос разрешения
    args += ["--model", os.environ.get("CLAUDE_BATCH_MODEL", "sonnet")]  # ночные батчи не на Opus
    for d in add_dirs:
        args += ["--add-dir", d]
    if schema is not None:
        args += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    s.data_dir.mkdir(parents=True, exist_ok=True)
    sysdirs = [] if os.name == "nt" else ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    env = {**os.environ, "PATH": os.pathsep.join([os.path.dirname(s.claude_bin), *sysdirs] + ([os.environ.get("PATH", "")] if os.name == "nt" else []))}
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(s.data_dir), env=env)
    except OSError as e:
        raise BrainError(f"не смог запустить claude: {e}")
    try:
        out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise BrainError(f"claude не ответил за {timeout} с")
    if proc.returncode != 0:
        raise BrainError(f"claude exit {proc.returncode}: {(err or out).decode(errors='ignore')[-300:]}")
    try:
        data = json.loads(out)
    except ValueError:
        raise BrainError("claude вернул не JSON")
    if data.get("is_error"):
        raise BrainError(f"claude: {str(data.get('result'))[:300]}")
    if schema is not None:
        so = data.get("structured_output")
        if not isinstance(so, dict):
            raise BrainError("claude не вернул structured_output")
        return so
    return str(data.get("result") or "")



# Формулировки из логов (You've hit your session/weekly limit · resets ...) и из бинаря claude 25.10.2026
_LIMIT = re.compile(r"hit your \w+ limit|limit reached|reached your \w+ (usage )?limit|out of extra usage|лимит|не смог запустить")


def is_limit(e: Exception) -> bool:
    """Лимит подписки или claude вообще не запускается: ночь обрывается, посты ждут без штрафа."""
    t = str(e).lower()
    if "context limit" in t or "usage:" in t:  # переполнен контекст / справка CLI при кривых флагах: это не лимит подписки
        return False
    return bool(_LIMIT.search(t))


async def run_claude_free(s: Settings, prompt: str, **kw):
    """Claude, а при лимите запасной бесплатный роутер (только для задач, где качество допускает замену)."""
    return await llm_fallback.with_fallback(run_claude, s, prompt, free_ok=True, is_limit=is_limit, **kw)
