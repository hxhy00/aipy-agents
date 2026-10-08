"""把 Markdown 代码块渲染成图片（微信公众号代码块方案 C）。

为什么用图片而不是 HTML：
    微信编辑器会折叠 HTML 源码里的换行符与连续空格，导致 <pre> 缩进丢失、
    长行被在字符中间硬折。用图片承载后，换行、缩进、语法高亮、长行的视觉呈现
    全部由图片本身保证，微信无法篡改像素。

实现（不自己写高亮算法，用成熟库；**不依赖浏览器**）：
    - 词法分析与语法高亮：Pygments（按语言猜 lexer，猜不到回退 text）
    - 出图：Pygments 自带的 ImageFormatter，内部用 Pillow 画 PNG
    - 字体：code_image_font 解析出的「可渲染中文」字体文件
      （Menlo/Consola/DejaVu Sans Mono 无 CJK 字形，中文注释会变空白）

为什么不用浏览器截图：
    早前方案靠无头浏览器渲染再截图，但那要求用户本机额外下载一份浏览器运行时
    （数百 MB），安装失败率很高（离线、权限、平台差异）。代码图只是静态文本加高亮，
    Pillow 完全够用，因此本模块**只依赖 pygments + Pillow，不需要任何浏览器**。
    如果将来遇到 Pillow 画不出的效果，也不要引入浏览器，改用其他出图方案。

cols 超宽处理策略（选定：软折行 + 极端情况硬切并标记）
    cols 是「每行最多多少个半角字符」，对应手机竖屏正文宽度。
    微信会在屏宽处硬折长行，把代码拦腰截断，缩进层级直接被破坏，所以
    必须在**源码层消灭超宽行**，绝不能靠 CSS 兜底。
    本模块的做法：
        1. 正常情况：按 cols 做软折行，优先在空格处断开，其次在 `,;)]}>` 之后断开，
           续行加 4 空格缩进（读起来能看出是折行而非真实换行）。内容零丢失，
           truncated=False。
        2. 极端情况：单个不可断的超长片段（长 URL、长 base64、长字符串字面量）
           连一个断点都没有，此时按显示列硬切，并置 truncated=True，
           同时在 warnings 里说明「该行在源码层被强制切断，读者看到的代码不完整，
           请在 Markdown 源码里把这行拆短后重新出图」。
    折行按**显示列**计算：CJK 字符占 2 列，避免中文注释行算窄了导致图片超宽。
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

from pygments import highlight as pyg_highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from .code_image_font import resolve_code_font

# 出图参数（可在 render_code_images 里覆盖）
DEFAULT_STYLE = "monokai"        # 深色主题，与原 HTML 配色一致
DEFAULT_FONT_SIZE = 15
IMAGE_PAD = 12                   # 图片四周留白（像素）
LINE_PAD = 4                     # 行间距（像素）

# 保护性上限：Pillow 对超大位图有实现上限，超过就跳过该块而不是让整个调用崩掉
MAX_RENDER_LINES = 600
MAX_IMAGE_EDGE = 20000

# 折行断点优先级：空格 > 收尾符号 > 强制按显示列切
_BREAK_AFTER = ",;)]}>"

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*(\S*)")


# ---------- 显示宽度 ----------


def _char_width(ch: str) -> int:
    """单个字符占的半角列数：东亚全角/宽字符算 2 列。"""
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _display_width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)


# ---------- 折行 ----------


def _hard_cut(text: str, budget: int) -> int:
    """在 budget 个显示列内找到硬切位置（保证至少切 1 个字符，避免死循环）。"""
    used = 0
    for i, ch in enumerate(text):
        w = _char_width(ch)
        if used + w > budget:
            return max(i, 1)
        used += w
    return len(text)


def _find_soft_break(text: str, budget: int) -> int:
    """在 budget 列内找最佳软断点，返回切分位置；找不到返回 0。

    优先级：空格 > `,;)]}>` 之后。返回的位置总是「切点之后」的下标。
    """
    used = 0
    space_cut = 0
    punct_cut = 0
    for i, ch in enumerate(text):
        w = _char_width(ch)
        if used + w > budget:
            break
        used += w
        if ch.isspace():
            space_cut = i + 1
        elif ch in _BREAK_AFTER:
            punct_cut = i + 1
    return space_cut or punct_cut


def _wrap_code_line(line: str, cols: int, cont_indent: str) -> tuple[list[str], bool]:
    """把一行源码折到 cols 显示列以内。

    返回 (折行后的物理行列表, 是否发生了强制硬切)。
    """
    if _display_width(line) <= cols:
        return [line], False

    # 续行至少留 8 列可用，否则折行没有意义（cols 传得太小），直接原样返回并标记
    budget = cols - _display_width(cont_indent)
    if budget < 8:
        return [line], True

    out: list[str] = []
    rest = line
    indent = ""  # 首行保持原样，续行才加缩进
    truncated = False

    while _display_width(rest) > budget:
        cut = _find_soft_break(rest, budget)
        if cut <= 0:
            # 没有任何可断点 → 只能硬切
            cut = _hard_cut(rest, budget)
            truncated = True
            out.append(indent + rest[:cut])
            rest = rest[cut:]
        else:
            out.append(indent + rest[:cut].rstrip())
            rest = rest[cut:].lstrip()
        indent = cont_indent

    out.append(indent + rest)
    return out, truncated


def _wrap_block(code: str, cols: int) -> tuple[str, bool, int]:
    """折行整个代码块，返回 (折行后源码, 是否硬切, 相对原始行数多出的行数)。"""
    cont_indent = "    "
    source_lines = code.split("\n")
    lines: list[str] = []
    truncated = False
    for raw in source_lines:
        leading = raw[: len(raw) - len(raw.lstrip())]
        wrapped, cut = _wrap_code_line(raw, cols, leading + cont_indent)
        truncated = truncated or cut
        lines.extend(wrapped)
    return "\n".join(lines), truncated, len(lines) - len(source_lines)


# ---------- 代码块抽取 ----------


def extract_code_blocks(md_text: str) -> list[dict]:
    """从 Markdown 中抽取围栏代码块，支持 ``` 与 ~~~ 两种围栏。

    返回 [{language, code}]，language 为 info string 的首段（可能是空串）。
    围栏按 CommonMark 规则处理：开围栏几字符，闭围栏至少同长且同字符。
    """
    blocks: list[dict] = []
    lines = md_text.split("\n")
    i = 0
    while i < len(lines):
        m = _FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fence, info = m.group(1), m.group(2)
        i += 1
        buf: list[str] = []
        while i < len(lines):
            close = _FENCE_RE.match(lines[i])
            # 闭合围栏不能带 info string，且长度不能短于开围栏
            if (
                close
                and close.group(1)[0] == fence[0]
                and len(close.group(1)) >= len(fence)
                and not close.group(2)
            ):
                i += 1
                break
            buf.append(lines[i])
            i += 1
        blocks.append({"language": info.split()[0] if info else "", "code": "\n".join(buf)})
    return blocks


def _pick_lexer(language: str):
    """按语言名取 lexer；猜不到（或未标注语言）回退 TextLexer。

    返回 (lexer, 实际生效的语言名, 是否按标注语言命中)。
    「实际生效的语言名」是回退后的 text —— 调用方要把它如实报给模型，
    否则模型会以为高亮生效了。
    """
    if not language:
        return TextLexer(), "text", False
    try:
        return get_lexer_by_name(language.lower()), language.lower(), True
    except ClassNotFound:
        return TextLexer(), "text", False


def _png_size(data: bytes) -> tuple[int, int]:
    """读出 PNG 像素尺寸。"""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        return im.size


# ---------- 出图 ----------


def render_code_images(
    md_path: str,
    out_dir: str,
    cols: int = 52,
    *,
    style: str = DEFAULT_STYLE,
    font_size: int = DEFAULT_FONT_SIZE,
    line_numbers: bool = False,
) -> dict:
    """把 Markdown 里的每个围栏代码块渲染成一张 PNG。

    参数：
        md_path:      Markdown 文件路径
        out_dir:      输出目录（不存在会自动创建）
        cols:         每行最多多少个半角字符，CJK 按 2 列计，默认 52
        style:        Pygments 配色风格名，默认 monokai（深色）
        font_size:    字号，默认 15
        line_numbers: 是否画行号栏，默认关闭（公众号读者一般不需要）

    返回 {ok, images, errors, warnings, out_dir}；
    images 每项为 {index, language, path, width, height, kb, lines,
                   rendered_lines, cols, truncated}。
    """
    images: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []

    src = Path(md_path).expanduser()
    if not src.is_file():
        return {
            "ok": False,
            "images": [],
            "errors": [f"Markdown 文件不存在：{md_path}"],
            "warnings": [],
            "out_dir": out_dir,
        }

    out = Path(out_dir).expanduser()
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {
            "ok": False,
            "images": [],
            "errors": [f"无法创建输出目录 {out_dir}：{e}"],
            "warnings": [],
            "out_dir": out_dir,
        }

    # 字体：中文字体缺失时必须显式告知，否则读者会看到「注释凭空消失」
    font_path, font_note = resolve_code_font()
    if font_path is None:
        warnings.append(
            f"{font_note}（本次已回退到系统默认字体出图，代码块中的中文可能显示为空白）"
        )
    else:
        warnings.append(font_note)

    try:
        blocks = extract_code_blocks(src.read_text(encoding="utf-8", errors="ignore"))
    except OSError as e:
        return {
            "ok": False,
            "images": [],
            "errors": [f"读取 Markdown 失败：{e}"],
            "warnings": warnings,
            "out_dir": str(out.resolve()),
        }

    if not blocks:
        return {
            "ok": True,
            "images": [],
            "errors": [],
            "warnings": warnings
            + ["未在 Markdown 中找到任何围栏代码块（``` 或 ~~~），没有生成图片。"],
            "out_dir": str(out.resolve()),
        }

    index = 0
    for block in blocks:
        raw_code = block["code"]
        if not raw_code.strip():
            warnings.append(f"第 {index + 1} 个代码块是空的，已跳过。")
            continue

        lexer, resolved_lang, guessed = _pick_lexer(block["language"])
        if block["language"] and not guessed:
            warnings.append(
                f"代码块 {index + 1} 标注的语言「{block['language']}」无法识别，"
                "已按纯文本渲染（无语法高亮）。建议改用 Pygments 支持的语言名。"
            )

        logical_lines = len(raw_code.split("\n"))
        if logical_lines > MAX_RENDER_LINES:
            errors.append(
                f"代码块 {index + 1} 有 {logical_lines} 行，超过单图上限 {MAX_RENDER_LINES} 行，"
                "已跳过。请在 Markdown 里拆成多个代码块分别出图。"
            )
            continue

        wrapped, truncated, extra_lines = _wrap_block(raw_code, cols)
        if extra_lines > 0 and not truncated:
            warnings.append(
                f"代码块 {index + 1} 有长行已按 cols={cols} 做源码层折行（多出 {extra_lines} 个视觉行，"
                "续行缩进 4 空格）。如不希望折行，请调大 cols 或在源码里手动拆行。"
            )
        if truncated:
            warnings.append(
                f"代码块 {index + 1} 存在超过 {cols} 列且无法在空格/标点处断行的片段"
                "（常见于长 URL、长 base64、长字符串字面量），已在显示列处强制切断，"
                "读者看到的该行代码不完整。请在 Markdown 源码里把这行拆短后重新出图。"
            )

        index += 1
        try:
            formatter = ImageFormatter(
                font_name=font_path or "",
                font_size=font_size,
                image_format="PNG",
                style=style,
                line_numbers=line_numbers,
                image_pad=IMAGE_PAD,
                line_pad=LINE_PAD,
            )
            data = pyg_highlight(wrapped, lexer, formatter)
        except Exception as e:  # noqa: BLE001 —— 字体/配色/编码等均可能在此抛错
            errors.append(
                f"代码块 {index} 渲染失败（语言：{block['language'] or 'text'}）："
                f"{type(e).__name__}: {e}"
            )
            continue

        path = out / f"code-{index}.png"
        try:
            path.write_bytes(data)
            width, height = _png_size(data)
        except Exception as e:  # noqa: BLE001
            errors.append(f"代码块 {index} 写图失败：{type(e).__name__}: {e}")
            continue

        if max(width, height) > MAX_IMAGE_EDGE:
            errors.append(
                f"代码块 {index} 出图尺寸 {width}x{height} 超过上限 {MAX_IMAGE_EDGE}px，已删除。"
                "请拆小该代码块后重试。"
            )
            path.unlink(missing_ok=True)
            continue

        images.append({
            "index": index,
            "language": resolved_lang,
            "path": str(path.resolve()),
            "width": width,
            "height": height,
            "kb": round(path.stat().st_size / 1024, 1),
            "lines": logical_lines,
            "cols": cols,
            "truncated": truncated,
        })

    return {
        "ok": not errors and bool(images),
        "images": images,
        "errors": errors,
        "warnings": warnings,
        "out_dir": str(out.resolve()),
    }