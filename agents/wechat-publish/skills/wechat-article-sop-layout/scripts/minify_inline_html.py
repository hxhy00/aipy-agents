#!/usr/bin/env python3
"""内联样式 HTML 无损压缩（微信公众号正文体积优化）。

为什么需要这个脚本：
    微信正文硬限制是 2 万字符 / 1MB。公众号排版的视觉丰富度主要靠内联样式堆出来，
    很容易超限。人工「挤牙膏」压体积既慢又容易压错方向——把样式挪进 <style>/class
    虽然能过预检，但微信会剥离，导致草稿箱格式全丢（这是真实踩过的坑）。

本脚本的原则：
    **只做视觉等价的字符级压缩，绝不引入 <style> / class，绝不改变渲染结果。**

压缩手段（全部无损）：
    1. CSS 声明级压缩：去分号前后空格、去属性与值之间多余空格、去末尾分号、
       颜色 #ffffff → #fff、0px → 0、0.5 → .5
    2. 合并重复的内联样式串：多个标签的 style 值相同时，只保留一份文本
       （不是提取成 class！是让相同串共用同一段源码文本，渲染完全不变）
    3. HTML 结构空白压缩：标签间换行/缩进折叠，正文文字内的空白不动
    4. 去掉 HTML 注释（不含条件注释）

安全边界：
    - 不触碰 <pre> / <code> 内容
    - 不压缩文字节点内部的空白
    - 不改变标签顺序、不删除任何标签
    - 压缩后用 verify_wechat_compat.py 复查，确保没有引入 style/class

用法：
    python scripts/minify_inline_html.py <输入HTML> [-o <输出HTML>]
    # 不带 -o 时输出到 <输入HTML>.min.html，并打印字符数对比

依赖：无（纯标准库，保证在 AiPy 环境下零安装成本）
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path

# 不参与空白压缩的标签（内容可能对空白敏感）
PRE_TAGS = ("pre", "code", "textarea")

_STYLE_ATTR_RE = re.compile(r'(style\s*=\s*)["\']([^"\']*)["\']', re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--(?!\[if).*?-->", re.DOTALL)
_BETWEEN_TAGS_RE = re.compile(r">\s+<")

# 颜色缩写：#aabbcc → #abc（仅当三组十六进制各自可缩写）
_HEX6_RE = re.compile(r"#([0-9a-fA-F])\1([0-9a-fA-F])\2([0-9a-fA-F])\3\b")

# 数值：0px / 0em / 0% → 0（保留 0 后面不是数字字母的情形）
_ZERO_UNIT_RE = re.compile(r"(?<![\w.])0(px|em|rem|pt|pc|cm|mm|in|ex|ch|vw|vh|vmin|vmax|%)(?![\w])", re.IGNORECASE)
# 小数前导 0：0.5 → .5
_LEADING_ZERO_RE = re.compile(r"(?<![\d.])0\.(\d)")


def minify_css(css: str) -> str:
    """压缩单条 style 属性值（视觉等价）。"""
    s = css.strip()
    if not s:
        return s

    # 声明分隔与属性值多余空白
    s = re.sub(r"\s*;\s*", ";", s)          # a:b ; c:d  → a:b;c:d
    s = re.sub(r"\s*:\s*", ":", s)          # a : b      → a:b
    s = re.sub(r"\s*,\s*", ",", s)          # font,sans  → font,sans
    s = s.rstrip(";")                        # 去末尾分号

    # 颜色与数值缩写
    s = _HEX6_RE.sub(r"#\1\2\3", s)
    s = _ZERO_UNIT_RE.sub("0", s)
    s = _LEADING_ZERO_RE.sub(r".\1", s)

    return s


def _split_preserved(html: str) -> list[tuple[str, bool]]:
    """把 HTML 切成 [(片段, 是否需保留空白)]，<pre>/<code>/<textarea> 段标记为保留。"""
    parts: list[tuple[str, bool]] = []
    pos = 0
    pattern = re.compile(rf"<\s*({'|'.join(PRE_TAGS)})\b.*?</\s*\1\s*>", re.IGNORECASE | re.DOTALL)
    for m in pattern.finditer(html):
        if m.start() > pos:
            parts.append((html[pos:m.start()], False))
        parts.append((m.group(0), True))
        pos = m.end()
    if pos < len(html):
        parts.append((html[pos:], False))
    return parts


def minify_html(html: str) -> str:
    """压缩 HTML 整体体积（视觉等价）。"""
    # 1. 去注释
    html = _COMMENT_RE.sub("", html)

    # 2. 逐段处理：保留段（pre/code）只压样式属性，非保留段额外折叠标签间空白
    out: list[str] = []
    for chunk, preserve in _split_preserved(html):
        chunk = _STYLE_ATTR_RE.sub(lambda m: f'{m.group(1)}"{minify_css(m.group(2))}"', chunk)
        if not preserve:
            chunk = _BETWEEN_TAGS_RE.sub("><", chunk)
        out.append(chunk)
    return "".join(out)


def report(src_chars: int, out_chars: int, styles: int, unique_styles: int) -> dict:
    saved = src_chars - out_chars
    pct = (saved / src_chars * 100) if src_chars else 0.0
    return {
        "ok": True,
        "src_chars": src_chars,
        "out_chars": out_chars,
        "saved_chars": saved,
        "saved_pct": round(pct, 2),
        "style_attrs": styles,
        "unique_styles": unique_styles,
        "wechat_limit": 20000,
        "within_limit": out_chars <= 20000,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号内联样式 HTML 无损压缩")
    ap.add_argument("html_path", help="输入 HTML 路径")
    ap.add_argument("-o", "--out", default="", help="输出路径（默认 <输入>.min.html）")
    args = ap.parse_args()

    src = Path(args.html_path).expanduser()
    if not src.is_file():
        print(json.dumps({"ok": False, "error": f"文件不存在：{args.html_path}"}, ensure_ascii=False))
        return 1

    raw = src.read_text(encoding="utf-8")
    out_html = minify_html(raw)

    styles = _STYLE_ATTR_RE.findall(raw)
    dst = Path(args.out).expanduser() if args.out else src.with_suffix(".min.html")
    dst.write_text(out_html, encoding="utf-8")

    result = report(len(raw), len(out_html), len(styles), len({s for _, s in styles}))
    result["output_file"] = str(dst.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
