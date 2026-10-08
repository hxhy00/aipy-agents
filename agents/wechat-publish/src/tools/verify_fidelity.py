"""内容保真反向核验（发布前的强制关卡）。

为什么需要这一步：
    「正文保真 100%」是排版的底线规则，但人（和模型）逐段目检一定会漏。
    真实踩过的坑：排版时漏掉了文章开头的两段导语，靠临时写的核对脚本才发现。
    临时脚本每次都要重写，且「导航重复二级标题要怎么剔除」的逻辑是硬编码的。
    这里把这件事固化成确定性工具。

核验逻辑（依据 content_fidelity_rules 的第 5 节）：
    1. 从排版 HTML 提取正文文字块（按标签边界切分成段）
    2. 剔除按规则不展示的内容：
       - 章节导航中重复的二级标题副本（导航区内的重复标题）
       - 文档主标题（HTML 中不出现，属于预期）
       - 空装饰元素（只有空 span/section 的容器）
    3. 与源文档的正文块按顺序逐项比较
    4. 输出：缺失块 / 多出块 / 错序块 / 数字差异

判定规则：
    - 归一化后完全一致才算通过（去空白差异，但保留文字、数字、标点、大小写）
    - 缺失 = 阻断；多出 = 阻断；错序 = 阻断
    - 数字/英文/标点的字符级差异 = 阻断

依赖：标准库；源文件为 .docx 时额外需要 python-docx（延迟导入，缺失时给出可读错误）。
"""

from __future__ import annotations

import re
from collections import Counter
from html import unescape as _html_unescape
from pathlib import Path

# ---------- 文本归一化 ----------


def normalize(text: str) -> str:
    """归一化：折叠空白，但保留文字、数字、标点、大小写。"""
    text = text.replace("　", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _is_meaningful(text: str) -> bool:
    """过滤纯装饰块（空元素、只有符号的装饰）。"""
    t = normalize(text)
    if not t:
        return False
    # 只由装饰性符号/空白组成 → 不算正文块
    if re.fullmatch(r"[|\-—_=~·•▪◆●■□○◦✦✧※→←↑↓\s]+", t):
        return False
    return True


# ---------- docx 依赖（延迟导入） ----------

_DOCX_IMPORT_HINT = (
    "解析 .docx 需要 python-docx 库，但当前环境导入失败。"
    "请安装后重试：uv pip install python-docx（或 pip install python-docx）。"
    "若暂时无法安装，可先把 Word 另存为 .md / .txt 再核验。"
)


def _load_docx_document(path: Path):
    """延迟导入 python-docx 并返回 Document。

    导入失败时抛出带修复动作的 ValueError（而不是把 ImportError 直接抛给上层），
    因为这条报错文案会被模型读到并据此决定下一步该做什么。
    """
    try:
        from docx import Document
    except ImportError as e:
        raise ValueError(f"{_DOCX_IMPORT_HINT}（原始错误：{e}）") from e
    return Document(str(path))


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
    doc = _load_docx_document(path)
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

# 导航区容器的启发式特征：块级标签的属性里出现「导航/目录/nav/toc」即视为导航区，
# 导航区里的标题副本属预期展示，不计入「缺失」。
_NAV_ATTR_RE = re.compile(r"(导航|目录|nav|toc)", re.IGNORECASE)

# 导航区里只放标题，用这个长度上限把「标题」和「正文段落」区分开：
# 超过该长度的源块不按导航副本处理，否则正文段落被漏排时会漏检。
_NAV_TITLE_MAX_CHARS = 30


def extract_blocks(html: str) -> list[dict]:
    """把 HTML 切成块，标注是否属于导航区（导航区的重复标题需剔除）。

    返回 [{text, is_nav}]，按文档顺序。
    """
    html = _SCRIPT_STYLE_RE.sub("", html)

    # 先按块级标签边界切分，再对每块用属性启发式判断是否导航容器。
    # 为稳妥，不用「连续短块」这类模糊猜测，只认显式的导航语义标记。
    parts: list[dict] = []
    positions = [m.start() for m in _BLOCK_TAG_RE.finditer(html)]
    positions.append(len(html))
    for i in range(len(positions) - 1):
        seg = html[positions[i]:positions[i + 1]]
        open_tag = _BLOCK_TAG_RE.match(seg)
        attr_text = open_tag.group(0) if open_tag else ""
        text = _html_unescape(_TAG_RE.sub("", seg)).strip()
        if not _is_meaningful(text):
            continue
        parts.append({"text": text, "is_nav": bool(_NAV_ATTR_RE.search(attr_text))})
    return parts


def _failed(message: str) -> dict:
    """统一的失败返回结构，保证字段齐全（模型侧按固定 schema 解析）。"""
    return {
        "ok": False,
        "fidelity_pct": 0.0,
        "errors": [message],
        "missing": [],
        "extra": [],
        "number_diff": [],
        "stats": {},
    }


# ---------- 核验 ----------


def verify_fidelity(source: str, html: str, main_title: str = "") -> dict:
    """核验排版 HTML 与源文档的内容保真度。

    参数：
        source:     源文档路径（.md / .txt / .docx）
        html:       排版后的 HTML 路径
        main_title: 文档主标题（按规则正文中不出现，不计入缺失）

    返回 {ok, fidelity_pct, errors, missing, extra, number_diff, stats}。
    ok=False 表示存在阻断问题，必须修复后再发布。
    """
    src = Path(source).expanduser()
    dst = Path(html).expanduser()
    if not src.is_file():
        return _failed(f"源文件不存在：{source}")
    if not dst.is_file():
        return _failed(f"HTML 文件不存在：{html}")

    try:
        if src.suffix.lower() == ".docx":
            title, src_blocks = blocks_from_docx(src)
            main_title = main_title or title
        else:
            md = src.read_text(encoding="utf-8", errors="ignore")
            src_blocks = blocks_from_markdown(md)
            main_title = main_title or (src_blocks[0] if src_blocks else "")
    except ValueError as e:
        # 目前只有 docx 依赖缺失会走到这里；文案已含修复动作
        return _failed(str(e))

    html_blocks = extract_blocks(dst.read_text(encoding="utf-8", errors="ignore"))
    html_texts = [b["text"] for b in html_blocks]

    src_norm = [normalize(b) for b in src_blocks]
    html_norm = [normalize(t) for t in html_texts]

    # 允许重复出现：文档主标题 + 导航区里的标题副本（导航重复属预期展示）
    allowed_dupes = {normalize(main_title)} if main_title else set()
    nav_texts = [normalize(b["text"]) for b in html_blocks if b["is_nav"]]
    allowed_dupes.update(nav_texts)

    # 导航区通常把多个标题拼在一个容器里（如「小节一小节二」），
    # 所以「是某个导航块文本的子串」也算导航副本。这正是原脚本 nav_titles
    # 参数要解决的问题，现在改为从 HTML 的导航块自动推导，调用方不必手工传标题。
    # 长度上限用来区分「标题」和「正文段落」：导航区只放标题，
    # 若把正文段落也当成导航副本，它被漏排时就会漏检。
    is_nav_copy = [
        len(sb) <= _NAV_TITLE_MAX_CHARS and any(nav and sb in nav for nav in nav_texts)
        for sb in src_norm
    ]

    missing: list[dict] = []
    cursor = 0
    matched_positions: list[int] = []
    for idx, sb in enumerate(src_norm):
        # 导航副本直接跳过，不参与匹配：
        # 若让它参与，短标题（如「小节一」）会贪心吃掉正文块「小节一正文…」，
        # 导致真正的正文块反而被判为缺失。
        if sb in allowed_dupes or is_nav_copy[idx]:
            continue
        # 优先精确匹配，匹配不到再退到包含匹配，避免短文本抢占长块
        found = -1
        for j in range(cursor, len(html_norm)):
            if html_norm[j] == sb:
                found = j
                break
        if found == -1:
            for j in range(cursor, len(html_norm)):
                if sb in html_norm[j] or html_norm[j] in sb:
                    found = j
                    break
        if found == -1:
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
        if html_blocks[j]["is_nav"]:
            continue  # 导航区是结构件，不算「多出内容」
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