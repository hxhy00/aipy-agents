#!/usr/bin/env python3
"""终稿解析脚本：把 Word(.docx) / Markdown(.md) / 纯文本(.txt) 统一转成 Markdown。

全流程 SOP 的第 1 步（确定性环节）。

用法：
    python scripts/read_draft.py <终稿路径> [--out <输出目录>]

输出：
    - 结构化摘要打印到 stdout（主标题 / 标题数 / 图片清单）
    - Markdown 正文写到 <终稿同目录>/<文件名>.parsed.md（或 --out 指定目录）
    - docx 内嵌图片抽取到 <终稿同目录>/images/

依赖：python-docx（仅解析 .docx 时需要）
    uv pip install python-docx   或   pip install python-docx
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

_HEADING_RE = re.compile(r"^Heading\s*(\d)$", re.IGNORECASE)
_CN_HEADING_RE = re.compile(r"^标题\s*(\d)$")


def _style_level(paragraph) -> int | None:
    """返回段落标题层级（1-9），非标题返回 None。兼容中英文样式名。"""
    style = paragraph.style
    if style is None or not style.name:
        return None
    name = style.name.strip()
    m = _HEADING_RE.match(name) or _CN_HEADING_RE.match(name)
    return int(m.group(1)) if m else None


def _iter_block_items(doc):
    """按文档原顺序迭代段落与表格。"""
    from docx.document import Document as _Doc
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = doc.element.body if isinstance(doc, _Doc) else doc
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def _extract_images(docx_path: Path, out_dir: Path) -> list[str]:
    """从 docx zip 结构中抽取 word/media/ 下的图片。"""
    names: list[str] = []
    try:
        with zipfile.ZipFile(docx_path) as z:
            media = [n for n in z.namelist() if n.startswith("word/media/") and not n.endswith("/")]
            if not media:
                return []
            img_dir = out_dir / "images"
            img_dir.mkdir(parents=True, exist_ok=True)
            for n in media:
                fname = Path(n).name
                (img_dir / fname).write_bytes(z.read(n))
                names.append(fname)
    except zipfile.BadZipFile:
        return []
    return names


def _table_to_markdown(table) -> str:
    rows = []
    for row in table.rows:
        rows.append([c.text.strip().replace("\n", " ") for c in row.cells])
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def parse_docx(path: Path) -> dict:
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(str(path))
    image_names = _extract_images(path, path.parent)
    image_paths = [str((path.parent / "images" / n).resolve()) for n in image_names]

    blocks: list[str] = []
    heading_seen = 0
    first_heading = ""
    first_para = ""

    for block in _iter_block_items(doc):
        if hasattr(block, "rows"):  # Table
            md = _table_to_markdown(block)
            if md:
                blocks.append(md)
            continue

        text = block.text.strip()
        has_drawing = bool(block._element.findall(".//" + qn("w:drawing")))
        if not text and not has_drawing:
            continue

        level = _style_level(block)
        if level is not None and text:
            heading_seen += 1
            if not first_heading:
                first_heading = text
            blocks.append("#" * min(level, 6) + " " + text)
            continue
        if text:
            if not first_para and not first_heading:
                first_para = text
            blocks.append(text)

    markdown = "\n\n".join(blocks)
    warnings: list[str] = []
    if image_names:
        refs = [f"![](images/{n})" for n in image_names]
        markdown += "\n\n" + "\n\n".join(refs)
        warnings.append("文档内嵌图片已抽取并附在文末，请确认插入位置与图注（图片来源需人工核对）。")
    if heading_seen == 0:
        warnings.append(
            "未识别到 Word 标题样式，章节导航会缺失；建议对标题应用「标题 1/标题 2」样式后重新导出。"
        )

    return {
        "markdown": markdown,
        "source_type": "docx",
        "title": first_heading or first_para,
        "heading_count": heading_seen,
        "image_paths": image_paths,
        "warnings": warnings,
    }


def parse_markdown(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()

    headings = re.findall(r"^#{1,6}\s+(.+)$", raw, re.MULTILINE)
    first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    warnings: list[str] = []

    if headings:
        title = headings[0]
    else:
        title = re.sub(r"^#+\s*", "", first_line)
        if raw:
            warnings.append("文档未使用 Markdown 标题（# / ##），章节导航会缺失；建议为标题行加 # 前缀。")

    # 收集 md 中引用的本地图片（相对当前目录）
    image_paths = [
        str((path.parent / m).resolve())
        for m in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", raw)
        if not m.startswith(("http://", "https://", "data:"))
    ]

    return {
        "markdown": raw,
        "source_type": "markdown",
        "title": title,
        "heading_count": len(headings),
        "image_paths": image_paths,
        "warnings": warnings,
    }


def parse_document(path_str: str) -> dict:
    p = Path(path_str).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"文件不存在：{path_str}")
    suffix = p.suffix.lower()
    if suffix == ".docx":
        return parse_docx(p)
    if suffix in (".md", ".markdown", ".txt"):
        return parse_markdown(p)
    if suffix == ".doc":
        raise ValueError("暂不支持旧版 .doc，请在 Word 中另存为 .docx 后重试。")
    raise ValueError(f"不支持的格式：{suffix}（支持 .docx / .md / .txt）")


def main() -> int:
    ap = argparse.ArgumentParser(description="终稿解析：docx/md/txt → Markdown")
    ap.add_argument("path", help="终稿文件路径")
    ap.add_argument("--out", default="", help="Markdown 输出目录（默认与终稿同目录）")
    args = ap.parse_args()

    try:
        result = parse_document(args.path)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        return 1

    src = Path(args.path).expanduser()
    out_dir = Path(args.out).expanduser() if args.out else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    md_file = out_dir / (src.stem + ".parsed.md")
    md_file.write_text(result["markdown"], encoding="utf-8")

    payload = {
        "ok": True,
        "source_type": result["source_type"],
        "title": result["title"],
        "heading_count": result["heading_count"],
        "image_paths": result["image_paths"],
        "warnings": result["warnings"],
        "markdown_file": str(md_file.resolve()),
        "markdown_preview": result["markdown"][:1500],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
