"""OCR для сервера по протоколу ocr_bin: пути картинок аргументами, блоки текста через ===== в stdout.
RapidOCR PP-OCRv5 (детектор) + eslav (русский, украинский, белорусский, болгарский). Замер 07.11.2026 на 30 картинках:
доля слов эталона 0.859 против 0.773 у Tesseract (tools/server-trial/bench/README.md).
Модели: RAPIDOCR_MODELS или <проект>/models (det.onnx, rec.onnx, dict.txt, HuggingFace monkt/paddleocr-onnx)."""
import contextlib
import io
import os
import sys
from pathlib import Path

from rapidocr import LangRec, OCRVersion, RapidOCR

M = Path(os.environ.get("RAPIDOCR_MODELS") or Path(__file__).resolve().parent.parent / "models")


def main(paths: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()):  # служебные сообщения движка не должны попасть в блоки
        eng = RapidOCR(params={"Det.model_path": str(M / "det.onnx"), "Det.ocr_version": OCRVersion.PPOCRV5,
                               "Rec.model_path": str(M / "rec.onnx"), "Rec.rec_keys_path": str(M / "dict.txt"),
                               "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.lang_type": LangRec.ESLAV})
    blocks = []
    for p in paths:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                r = eng(p)
            blocks.append("\n".join(r.txts) if r is not None and r.txts else "")
        except Exception as e:  # noqa: BLE001 битая картинка не должна ронять весь вызов
            print(f"ocr {p}: {e}", file=sys.stderr)
            blocks.append("")
    print("\n=====\n".join(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
