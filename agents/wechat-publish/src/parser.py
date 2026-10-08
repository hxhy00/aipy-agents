"""终稿解析：把 Word(.docx) / Markdown(.md) / 纯文本(.txt) 统一转换成 Markdown。

为什么需要这一步：
    排版的输入是「带标题层级的结构化文本」，而 .docx 本质是 zip 压缩包，
    AI 无法直接读取。本模块把终稿解析成 Markdown（标题用 #/## 表达层级、
    图片抽取为 ![](文件名) 引用），交给排版环节做章节导航与视觉排版。

实现选型：
    - .docx 使用成熟库 python-docx 解析（标题层级 / 段落 / 内嵌图片）；
    - .md / .txt 为纯文本，直接读取并做轻量规整。

输出约定（与排版环节的输入要求对齐）：
    - 一级标题 -> "## "（正文里不出现文章主标题，主标题由 publish_draft 的 title 承载）
    - Word 的 Heading 1 -> Markdown 一级标题（"# "），Heading 2/3 -> 对应 ""##"/"###"" 层级
    - 内嵌图片抽取到同级 images/ 目录，正文以 ![](images/文件名) 引用

两种消费方式：
    - 直接把 markdown 字段回给模型（parse_document 默认行为）；
    - 需要落盘给其他工具接着处理时，用 dump_markdown=True 额外写出
      <stem>.parsed.md，返回值里的 markdown_file 字段给出绝对路径。
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

# ---------- 数据结构 ----------

@dataclass
class ParseResult:
    markdown: str                          # 解析出的 Markdown 正文
    source_type: str                       # docx / markdown / text
    title: str = ""                        # 从文档中推断出的文章主标题（首个 Heading1 或首个非空行）
    heading_count: int = 0                 # 标题总数（用于自检层级是否被识别）
    image_paths: list[str] = field(default_factory=list)  # 抽取/收集到的图片绝对路径
    warnings: list[str] = field(default_factory=list)
    markdown_file: str = ""                # 落盘时的 <stem>.parsed.md 绝对路径（未落盘则为空）

    def summary(self) -> str:
        lines = [
            f"解析完成（类型：{self.source_type}）",
            f"- 主标题：{self.title or '（未识别到，请人工指定）'}",
            f"- 识别到标题 {self.heading_count} 个",
            f"- 抽取图片 {len(self.image_paths)} 张",
        ]
        if self.image_paths:
            lines.append("- 图片文件：")
            lines.extend(f"    {p}" for p in self.image_paths)
        if self.markdown_file:
            lines.append(f"- Markdown 已落盘：{self.markdown_file}")
        if self.warnings:
            lines.append("- 提示：")
            lines.extend(f"    {w}" for w in self.warnings)
        return "\n".join(lines)


# ---------- docx 解析 ----------

_HEADING_RE = re.compile(r"^Heading\s*(\d)$", re.IGNORECASE)


def _style_level(paragraph) -> int | None:
    """返回段落的标题层级（1-9），非标题返回 None。"""
    style = paragraph.style
    if style is None or not style.name:
        return None
    m = _HEADING_RE.match(style.name.strip())
    if m:
        return int(m.group(1))
    # 中文版 Word 的样式名可能是「标题 1」
    m = re.match(r"^标题\s*(\d)$", style.name.strip())
    if m:
        return int(m.group(1))
    return None


def _iter_block_items(doc):
    """按文档顺序迭代段落与表格（python-docx 默认分开存放，这里合并为原顺序）。"""
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
    """从 docx 的 zip 结构中抽取 media 图片，返回相对引用名列表（按 media 原始名）。"""
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
    """把 Word 表格转成 Markdown 表格。"""
    rows = []
    for row in table.rows:
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def parse_docx(docx_path: Path) -> ParseResult:
    """解析 Word 文档为 Markdown。"""
    result = ParseResult(markdown="", source_type="docx")
    if not docx_path.is_file():
        raise FileNotFoundError(f"文件不存在：{docx_path}")

    doc = Document(str(docx_path))
    image_names = _extract_images(docx_path, docx_path.parent)
    result.image_paths = [str((docx_path.parent / "images" / n).resolve()) for n in image_names]

    blocks: list[str] = []
    heading_seen = 0
    first_heading: str = ""
    first_para: str = ""

    for block in _iter_block_items(doc):
        if hasattr(block, "rows"):  # Table
            md = _table_to_markdown(block)
            if md:
                blocks.append(md)
            continue

        para = block
        text = para.text.strip()
        # 段落内嵌图片：统计 drawing 数量，按抽取顺序补引用（仅顶层引用，避免重复）
        has_drawing = bool(para._element.findall(".//" + qn("w:drawing")))

        if not text and not has_drawing:
            continue

        level = _style_level(para)
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

    # 内嵌图片统一在文末列出，交由 AI 决定插入位置（图注/位置需人工判断）
    if image_names:
        refs = [f"![](images/{n})" for n in image_names]
        markdown += "\n\n" + "\n\n".join(refs)
        result.warnings.append("文档内嵌图片已抽取并附在文末，请确认插入位置与图注（图片来源需人工核对）。")

    result.markdown = markdown
    result.title = first_heading or first_para
    result.heading_count = heading_seen
    if heading_seen == 0:
        result.warnings.append(
            "未识别到 Word 标题样式。当前排版只能按段落处理，章节导航会缺失；"
            "建议在 Word 中对标题应用「标题 1/标题 2」样式后重新上传。"
        )
    return result


# ---------- md / txt 解析 ----------

# Markdown 里的本地图片引用 ![alt](path)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
# 不是本地文件的引用（外链 / base64），排版时微信会过滤掉，不计入 image_paths
_REMOTE_IMAGE_PREFIXES = ("http://", "https://", "data:")


def parse_markdown(md_path: Path) -> ParseResult:
    """读取 Markdown/TXT，做轻量规整。"""
    result = ParseResult(markdown="", source_type="markdown")
    if not md_path.is_file():
        raise FileNotFoundError(f"文件不存在：{md_path}")
    raw = md_path.read_text(encoding="utf-8", errors="ignore")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()

    headings = re.findall(r"^#{1,6}\s+(.+)$", raw, re.MULTILINE)
    result.heading_count = len(headings)

    first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    if headings:
        result.title = headings[0]
    else:
        result.title = re.sub(r"^#+\s*", "", first_line)
        if raw and not headings:
            result.warnings.append(
                "文档未使用 Markdown 标题（# / ##），章节导航会缺失；建议为标题行加 # 前缀。"
            )

    # 收集 md 中引用的本地图片（相对当前文件所在目录），并标出缺失的文件
    local_refs = [
        m.strip()
        for m in _MD_IMAGE_RE.findall(raw)
        if not m.strip().startswith(_REMOTE_IMAGE_PREFIXES)
    ]
    missing: list[str] = []
    for ref in local_refs:
        candidate = Path(ref)
        if not candidate.is_absolute():
            candidate = (md_path.parent / ref).resolve()
        result.image_paths.append(str(candidate))
        if not candidate.is_file():
            missing.append(ref)
    if missing:
        result.warnings.append(
            f"以下图片引用在本地不存在（{len(missing)} 张）：{'；'.join(missing[:5])}。"
            "发布时会导致图片空白，请先补齐或移除引用。"
        )
    remote = len(_MD_IMAGE_RE.findall(raw)) - len(local_refs)
    if remote > 0:
        result.warnings.append(
            f"文档中有 {remote} 处外链/base64 图片引用：微信会过滤为空白，"
            "请下载到本地并改为本地路径引用。"
        )

    result.markdown = raw
    return result


# ---------- 统一入口 ----------

def parse_document(path: str, dump_markdown: bool = False, out_dir: str = "") -> ParseResult:
    """按扩展名分派解析。支持 .docx / .md / .markdown / .txt。

    参数：
        path:          终稿文件路径
        dump_markdown: 是否把解析结果落盘为 <stem>.parsed.md（默认 False）
        out_dir:       落盘目录，默认与终稿同目录

    返回的 ParseResult.markdown_file 在落盘时给出绝对路径。
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"文件不存在：{path}")
    suffix = p.suffix.lower()
    if suffix == ".docx":
        result = parse_docx(p)
    elif suffix in (".md", ".markdown", ".txt"):
        result = parse_markdown(p)
    elif suffix == ".doc":
        raise ValueError("暂不支持旧版 .doc 格式，请在 Word 中另存为 .docx 后重试。")
    else:
        raise ValueError(f"不支持的格式：{suffix}（支持 .docx / .md / .txt）")

    if dump_markdown:
        target_dir = Path(out_dir).expanduser() if out_dir else p.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        md_file = target_dir / (p.stem + ".parsed.md")
        md_file.write_text(result.markdown, encoding="utf-8")
        result.markdown_file = str(md_file.resolve())

    return result
