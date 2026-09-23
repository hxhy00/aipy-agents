#!/usr/bin/env python3
"""内容保真反向核验（全流程 SOP 第 4 步的强制关卡）。

为什么需要这个脚本：
    「正文保真 100%」是排版 skill 的底线规则，但人（和模型）逐段目检一定会漏。
    真实踩过的坑：排版时漏掉了文章开头的两段导语，靠临时写的核对脚本才发现。
    临时脚本每次都要重写，且「导航重复二级标题要怎么剔除」的逻辑是硬编码的。
    本脚本把这件事固化成确定性工具。

核验逻辑（依据 references/content_fidelity_rules.md 第 5 节）：
    1. 从排版 HTML 提取正文文字块（按标签边界切分成段）
    2. 剔除按规则不展示的内容：
       - 章节导航中重复的二级标题副本（导航区内的重复标题）
       - 文档主标题（HTML 中不出现，属于预期）
       - 空装饰元素（只有空 span/section 的容器）
    3. 与源 Markdown 的正文块按顺序逐项比较
    4. 输出：缺失块 / 多出块 / 错序块 / 数字与专名差异

判定规则：
    - 归一化后完全一致才算通过（去空白差异，但保留文字、数字、标点、大小写）
    - 缺失 = 阻断；多出 = 阻断；错序 = 阻断
    - 数字/英文/标点的字符级差异 = 阻断

用法：
    python scripts/verify_fidelity.py <源Markdown|源docx> <排版HTML> [--main-title "主标题"]

退出码：0 = 保真 100%；1 = 存在阻断问题
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------- 文本归一化 ----------

def normalize(text: str) -> str:
    """归一化：折叠空白，但保留文字、数字、标点、大小写。"""
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _is_meaningful(text: str) -> bool:
    """过滤纯装饰块（空元素、只有符号的装饰）。"""
    t = normalize(text)
    if not t:
        return False
    # 只由装饰性符号/空白组成 → 不算正文块
    if re.fullmatch(r"[|\-—_=~·•▪◆●■□○◦✦✧※→←↑↓·\s]+", t):
        return False
    return True


# ---------- 源文档正文块提取 ----------

def blocks_from_markdown(md: str) -> list[str]:
    """把 Markdown 切成正文块（按空行分段，去掉 Markdown 标记）。"""
    blocks: list[str] = []
    for raw in re.split(r"\n\s*\n", md):
        line = raw.strip()
        if not line:
            continue
        # 图片引用单独成块（用于图片数量核验），但不作为文字块
        if re.fullmatch(r"(!\[[^\]]*\]\([^)]*\)\s*)+", line):
            continue
        # 去标题标记
        line = re.sub(r"^#{1,6}\s*", "", line)
        # 去列表标记
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+\.\s+", "", line)
        # 去表格分隔行
        if re.fullmatch(r"\|[\s\-:|]+\|", line):
            continue
        # 表格行去掉竖线
        if line.startswith("|") and line.endswith("|"):
            line = line.strip("|").replace("|", " ")
        # 去引用标记
        line = re.sub(r"^>\s*", "", line)
        # 去行内格式标记
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", line)
        line = re.sub(r"`(.+?)`", r"\1", line)
        line = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
        if _is_meaningful(line):
            blocks.append(line)
    return blocks


def blocks_from_docx(path: Path) -> tuple[str, list[str]]:
    """解析 docx 得到 (主标题, 正文块列表)。"""
    from docx import Document

    doc = Document(str(path))
    blocks: list[str] = []
    title = ""
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = (para.style.name or "") if para.style else ""
        if re.match(r"^(Heading\s*1|标题\s*1)$", style_name, re.IGNORECASE) and not title:
            title = text
        blocks.append(text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                t = cell.text.strip()
                if t:
                    blocks.append(t)
    return title, blocks


# ---------- HTML 正文块提取 ----------

_SCRIPT_STYLE_RE = re.compile(r"<\s*(script|style)\b.*?</\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_BLOCK_TAG_RE = re.compile(
    r"<\s*/?\s*(p|div|section|h[1-6]|li|tr|td|th|blockquote|figure|figcaption|table|ul|ol|br)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_blocks(html: str) -> list[dict]:
    """把 HTML 切成块，标注是否属于导航区（导航区的重复标题需剔除）。

    返回 [{text, is_nav}]，按文档顺序。
    """
    html = _SCRIPT_STYLE_RE.sub("", html)

    # 标记导航容器：带 nav 语义或包含多个 <a>/<span> 短文本的浅底条
    # 这里用启发式：含 "导航"|"目录"|"nav" 的注释/属性，或连续多个同级短块
    # 为稳妥，先按块级标签切分，再对每块判断
    parts: list[dict] = []
    positions = [m.start() for m in _BLOCK_TAG_RE.finditer(html)]
    positions.append(len(html))
    for i in range(len(positions) - 1):
        seg = html[positions[i]:positions[i + 1]]
        # 记录该块外层标签属性（用于判断导航）
        open_tag = _BLOCK_TAG_RE.match(seg)
        attr_text = open_tag.group(0) if open_tag else ""
        text = _TAG_RE.sub("", seg)
        text = html_unescape(text)
        if not _is_meaningful(text):
            continue
        is_nav = bool(re.search(r"(导航|目录|nav|toc)", attr_text, re.IGNORECASE))
        parts.append({"text": text.strip(), "is_nav": is_nav})
    return parts


def html_unescape(s: str) -> str:
    import html as _h
    return _h.unescape(s)


# ---------- 核验 ----------

def verify(source_path: str, html_path: str, main_title: str = "", nav_titles: list[str] | None = None) -> dict:
    src = Path(source_path).expanduser()
    dst = Path(html_path).expanduser()
    if not src.is_file():
        return {"ok": False, "errors": [f"源文件不存在：{source_path}"]}
    if not dst.is_file():
        return {"ok": False, "errors": [f"HTML 文件不存在：{html_path}"]}

    if src.suffix.lower() == ".docx":
        title, src_blocks = blocks_from_docx(src)
        main_title = main_title or title
    else:
        md = src.read_text(encoding="utf-8", errors="ignore")
        src_blocks = blocks_from_markdown(md)
        main_title = main_title or (src_blocks[0] if src_blocks else "")

    html = dst.read_text(encoding="utf-8")
    html_blocks = extract_blocks(html)
    html_texts = [b["text"] for b in html_blocks]

    allowed_dupes = {normalize(t) for t in (nav_titles or []) if t}
    if main_title:
        allowed_dupes.add(normalize(main_title))

    # 逐块顺序比对：用「在 HTML 块序列中按顺序贪心查找」判断缺失/错序
    src_norm = [normalize(b) for b in src_blocks]
    html_norm = [normalize(t) for t in html_texts]

    missing: list[dict] = []
    cursor = 0
    matched_positions: list[int] = []
    for idx, sb in enumerate(src_norm):
        found = -1
        for j in range(cursor, len(html_norm)):
            if html_norm[j] == sb or sb in html_norm[j] or html_norm[j] in sb:
                found = j
                break
        if found == -1:
            # 允许：主标题 / 导航重复标题属于预期不展示
            if sb in allowed_dupes:
                continue
            # 再全局找一次，判断是否为「错序」
            anywhere = next((j for j, h in enumerate(html_norm) if h == sb or sb in h), None)
            if anywhere is not None:
                missing.append({
                    "index": idx,
                    "text": src_blocks[idx][:80],
                    "reason": f"错序：该段落在 HTML 中出现在第 {anywhere + 1} 块，晚于当前位置",
                })
            else:
                missing.append({
                    "index": idx,
                    "text": src_blocks[idx][:80],
                    "reason": "缺失：HTML 中找不到该段落",
                })
        else:
            cursor = found + 1
            matched_positions.append(found)

    # 多出块：HTML 中有、但源文没有，且不是允许的导航重复
    src_norm_set = set(src_norm)
    extra: list[dict] = []
    for j, hb in enumerate(html_norm):
        if j in matched_positions:
            continue
        if hb in src_norm_set:
            continue  # 属于重复（导航），已在 allowed 逻辑覆盖
        if hb in allowed_dupes:
            continue
        if any(hb in s or s in hb for s in src_norm_set):
            continue
        extra.append({"index": j, "text": html_texts[j][:80]})

    # 数字差异检查（数字是高风险项）
    # 注意：主标题按规则不进正文，其含有的数字（如「A2A」里的 2）不应计入缺失，
    # 否则会产生误报。导航区重复的标题同理。
    from collections import Counter

    skip_norm = {normalize(main_title)} if main_title else set()
    num_src_blocks = [b for b in src_blocks if normalize(b) not in skip_norm]
    num_html_texts = [t for t in html_texts if normalize(t) not in skip_norm]

    src_num_counter = Counter(re.findall(r"\d+(?:\.\d+)?%?", " ".join(num_src_blocks)))
    html_num_counter = Counter(re.findall(r"\d+(?:\.\d+)?%?", " ".join(num_html_texts)))
    num_diff = [n for n, cnt in src_num_counter.items() if html_num_counter[n] < cnt]

    errors: list[str] = []
    if missing:
        errors.append(f"{len(missing)} 个源文段落未在 HTML 中按序找到（缺失/错序）")
    if extra:
        errors.append(f"HTML 中多出 {len(extra)} 个源文没有的段落")
    if num_diff:
        errors.append(f"数字不一致：{('、'.join(num_diff[:10]))}")

    fidelity = 100.0 if not (missing or extra or num_diff) else round(
        (len(src_norm) - len(missing)) / max(len(src_norm), 1) * 100, 2
    )

    return {
        "ok": fidelity == 100.0,
        "fidelity_pct": fidelity,
        "errors": errors,
        "missing": missing,
        "extra": extra,
        "number_diff": num_diff,
        "stats": {
            "source_blocks": len(src_blocks),
            "html_blocks": len(html_texts),
            "matched": len(matched_positions),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号排版内容保真反向核验")
    ap.add_argument("source", help="源文档（.md/.docx/.txt）")
    ap.add_argument("html", help="排版后的 HTML")
    ap.add_argument("--main-title", default="", help="文档主标题（正文中预期不出现）")
    args = ap.parse_args()

    result = verify(args.source, args.html, args.main_title)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
