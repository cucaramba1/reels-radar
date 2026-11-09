#!/bin/bash
# Обёртка для ocr_bin: run_ocr вызывает исполняемый файл, а нам нужен python из .venv проекта.
D="$(cd "$(dirname "$0")/.." && pwd)"
exec "$D/.venv/bin/python" "$D/scripts/ocr_rapid.py" "$@"
