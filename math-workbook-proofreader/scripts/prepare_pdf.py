#!/usr/bin/env python3
"""Render body and optional answer PDFs for Codex-assisted proofreading."""

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


def prepare_document(
    pdf_path: Path,
    work_dir: Path,
    document_id: str,
    label: str,
    scale: float,
    pdftoppm: str,
) -> dict:
    if not pdf_path.is_file():
        raise FileNotFoundError(f"找不到{label} PDF：{pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"{label}文件必须是 PDF。")

    role_root = work_dir / document_id
    pages_dir = role_root / "pages"
    text_dir = role_root / "text"
    blocks_dir = role_root / "blocks"
    for directory in (pages_dir, text_dir, blocks_dir):
        directory.mkdir(parents=True, exist_ok=True)

    dpi = round(72 * scale)
    try:
        document = pdfplumber.open(pdf_path)
    except Exception as exc:
        raise ValueError(f"无法打开{label} PDF；文件可能损坏或已加密。") from exc

    manifest_pages: list[dict] = []
    with document:
        for index, page in enumerate(document.pages, start=1):
            width, height = float(page.width), float(page.height)
            image_name = f"page-{index:04d}.png"
            text_name = f"page-{index:04d}.txt"
            blocks_name = f"page-{index:04d}.json"

            subprocess.run(
                [
                    pdftoppm,
                    "-f", str(index),
                    "-l", str(index),
                    "-singlefile",
                    "-png",
                    "-r", str(dpi),
                    str(pdf_path),
                    str(pages_dir / f"page-{index:04d}"),
                ],
                check=True,
                capture_output=True,
            )

            extraction_error = None
            try:
                words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
            except Exception as exc:
                words = []
                extraction_error = str(exc)
            blocks = []
            extracted_parts = []
            for word in words:
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
                    "image": f"pages/{document_id}/{image_name}",
                    "work_image": f"{document_id}/pages/{image_name}",
                    "text": f"{document_id}/text/{text_name}",
                    "blocks": f"{document_id}/blocks/{blocks_name}",
                    "extracted_characters": len(extracted_text),
                    "likely_scanned": len(extracted_text.strip()) < 20,
                    "image_sha256": sha256(pages_dir / image_name),
                    "extraction_error": extraction_error,
                }
            )

    return {
        "id": document_id,
        "role": document_id,
        "label": label,
        "source_name": pdf_path.name,
        "source_sha256": sha256(pdf_path),
        "page_count": len(manifest_pages),
        "pages": manifest_pages,
    }


def prepare(body: Path, answer: Path | None, work_dir: Path, scale: float) -> Path:
    if scale < 1.0 or scale > 4.0:
        raise ValueError("--scale 必须在 1.0 到 4.0 之间。")
    if answer and body.resolve() == answer.resolve():
        raise ValueError("正文与答案是同一个 PDF 时，请只传 --body。")
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("缺少 Poppler 的 pdftoppm，无法渲染 PDF 页面。")

    work_dir.mkdir(parents=True, exist_ok=True)
    old_path = work_dir / "manifest.json"
    if old_path.exists():
        old = json.loads(old_path.read_text(encoding="utf-8-sig"))
        expected = [("body", sha256(body))] + ([("answer", sha256(answer))] if answer else [])
        actual = [(d["id"], d["source_sha256"]) for d in old["documents"]]
        if expected != actual or old.get("render_scale") != scale:
            raise ValueError("PDF 或渲染倍率已变化，请使用新的工作目录，避免覆盖封存校对结果。")
        intact = all((work_dir / p[key]).is_file() for d in old["documents"] for p in d["pages"]
                     for key in ("work_image", "text", "blocks"))
        intact = intact and all(not p.get("image_sha256") or sha256(work_dir / p["work_image"]) == p["image_sha256"]
                                for d in old["documents"] for p in d["pages"])
        if intact:
            print(f"复用未变化的预处理结果：{old_path}")
            return old_path
        raise ValueError("预处理资源缺失或变化；请在新目录重新准备，保留当前审计记录。")
    documents = [prepare_document(body, work_dir, "body", "正文", scale, pdftoppm)]
    if answer:
        documents.append(prepare_document(answer, work_dir, "answer", "答案", scale, pdftoppm))

    manifest = {
        "version": 2,
        "audit_required": True,
        "render_scale": scale,
        "document_count": len(documents),
        "page_count": sum(document["page_count"] for document in documents),
        "documents": documents,
    }
    manifest_path = work_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = []
    for document in documents:
        scanned = sum(1 for page in document["pages"] if page["likely_scanned"])
        summary.append(f"{document['label']} {document['page_count']} 页（疑似扫描页 {scanned}）")
    print("已准备：" + "；".join(summary) + "。")
    print(f"清单：{manifest_path}")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="预处理数学教辅正文和可选答案 PDF。")
    parser.add_argument("--body", required=True, type=Path, help="正文 PDF")
    parser.add_argument("--answer", type=Path, help="答案或解析 PDF，可省略")
    parser.add_argument("--work-dir", required=True, type=Path, help="工作目录")
    parser.add_argument("--scale", type=float, default=2.0, help="页面渲染倍率，默认 2.0")
    args = parser.parse_args()
    try:
        prepare(
            args.body.resolve(),
            args.answer.resolve() if args.answer else None,
            args.work_dir.resolve(),
            args.scale,
        )
    except Exception as exc:
        print(f"处理失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
