#!/usr/bin/env python3
"""Render a PDF and extract page text blocks for Codex-assisted proofreading."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover - environment dependent
    print("缺少 pdfplumber。请先运行：python -m pip install pdfplumber", file=sys.stderr)
    raise SystemExit(2)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_bbox(word: dict, width: float, height: float) -> dict[str, float]:
    x0, y0, x1, y1 = word["x0"], word["top"], word["x1"], word["bottom"]
    return {
        "x": round(max(0.0, x0 / width), 6),
        "y": round(max(0.0, y0 / height), 6),
        "width": round(max(0.0, (x1 - x0) / width), 6),
        "height": round(max(0.0, (y1 - y0) / height), 6),
    }


def prepare(pdf_path: Path, work_dir: Path, scale: float) -> Path:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"找不到 PDF：{pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("输入文件必须是 PDF。")
    if scale < 1.0 or scale > 4.0:
        raise ValueError("--scale 必须在 1.0 到 4.0 之间。")

    pages_dir = work_dir / "pages"
    text_dir = work_dir / "text"
    blocks_dir = work_dir / "blocks"
    for directory in (pages_dir, text_dir, blocks_dir):
        directory.mkdir(parents=True, exist_ok=True)

    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("缺少 Poppler 的 pdftoppm，无法渲染 PDF 页面。")
    dpi = round(72 * scale)
    manifest_pages: list[dict] = []
    try:
        document = pdfplumber.open(pdf_path)
    except Exception as exc:
        raise ValueError("无法打开 PDF；文件可能损坏或已加密。") from exc

    with document:
        for index, page in enumerate(document.pages, start=1):
            width, height = float(page.width), float(page.height)
            image_name = f"page-{index:04d}.png"
            text_name = f"page-{index:04d}.txt"
            blocks_name = f"page-{index:04d}.json"

            output_prefix = pages_dir / f"page-{index:04d}"
            subprocess.run(
                [
                    pdftoppm,
                    "-f", str(index),
                    "-l", str(index),
                    "-singlefile",
                    "-png",
                    "-r", str(dpi),
                    str(pdf_path),
                    str(output_prefix),
                ],
                check=True,
                capture_output=True,
            )

            raw_words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
            blocks = []
            extracted_parts = []
            for word in raw_words:
                text = str(word.get("text", "")).strip()
                if not text:
                    continue
                extracted_parts.append(text)
                blocks.append({"text": text, "bbox": normalized_bbox(word, width, height)})

            extracted_text = "\n".join(extracted_parts)
            (text_dir / text_name).write_text(extracted_text, encoding="utf-8")
            (blocks_dir / blocks_name).write_text(
                json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            manifest_pages.append(
                {
                    "page": index,
                    "width": round(width, 3),
                    "height": round(height, 3),
                    "image": f"pages/{image_name}",
                    "text": f"text/{text_name}",
                    "blocks": f"blocks/{blocks_name}",
                    "extracted_characters": len(extracted_text),
                    "likely_scanned": len(extracted_text.strip()) < 20,
                }
            )
    manifest = {
        "source_name": pdf_path.name,
        "source_sha256": sha256(pdf_path),
        "page_count": len(manifest_pages),
        "render_scale": scale,
        "pages": manifest_pages,
    }
    manifest_path = work_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    scanned = sum(1 for page in manifest_pages if page["likely_scanned"])
    print(f"已准备 {len(manifest_pages)} 页；疑似扫描页 {scanned} 页。")
    print(f"清单：{manifest_path}")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="将数学教辅 PDF 渲染为校对工作文件。")
    parser.add_argument("pdf", type=Path, help="输入 PDF")
    parser.add_argument("--work-dir", required=True, type=Path, help="工作目录")
    parser.add_argument("--scale", type=float, default=2.0, help="页面渲染倍率，默认 2.0")
    args = parser.parse_args()
    try:
        prepare(args.pdf.resolve(), args.work_dir.resolve(), args.scale)
    except Exception as exc:
        print(f"处理失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
