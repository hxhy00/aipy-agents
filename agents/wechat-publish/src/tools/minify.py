"""内联样式 HTML 无损压缩（微信公众号正文体积优化）。

为什么需要这一步：
    微信正文硬限制是 2 万字符 / 1MB。公众号排版的视觉丰富度主要靠内联样式堆出来，
    很容易超限。人工「挤牙膏」压体积既慢又容易压错方向——把样式挪进 <style>/class
    虽然能过预检，但微信会剥离，导致草稿箱格式全丢（这是真实踩过的坑）。

本模块的原则：
    **只做视觉等价的字符级压缩，绝不引入 <style> / class，绝不改变渲染结果。**

压缩手段（全部无损）：
    1. CSS 声明级压缩：去分号前后空格、去属性与值之间多余空格、去末尾分号、
       颜色 #ffffff → #fff、0px → 0、0.5 → .5
    2. HTML 结构空白压缩：标签间换行/缩进折叠，正文文字内的空白不动
    3. 去掉 HTML 注释（不含条件注释）

安全边界：
    - 不触碰 <pre> / <code> / <textarea> 内容
    - 不压缩文字节点内部的空白
    - 不改变标签顺序、不删除任何标签
    - 压缩后建议再跑一次微信兼容性校验，确保没有引入 style/class

依赖：无（纯标准库）。
"""

from __future__ import annotations

import re
from pathlib import Path

# 微信正文硬限制
WECHAT_CONTENT_CHARS = 20000

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


def minify_inline_html(html_path: str, out_path: str = "") -> dict:
    """无损压缩内联样式 HTML，返回压缩统计。

    参数：
        html_path: 输入 HTML 路径
        out_path:  输出路径；留空则写到 <输入>.min.html

    返回 {ok, src_chars, out_chars, saved_chars, saved_pct, style_attrs,
          unique_styles, wechat_limit, within_limit, output_file}。
    """
    src = Path(html_path).expanduser()
    if not src.is_file():
        return {
            "ok": False,
            "error": f"文件不存在：{html_path}",
            "src_chars": 0,
            "out_chars": 0,
            "saved_chars": 0,
            "saved_pct": 0.0,
            "style_attrs": 0,
            "unique_styles": 0,
            "wechat_limit": WECHAT_CONTENT_CHARS,
            "within_limit": False,
            "output_file": "",
        }

    raw = src.read_text(encoding="utf-8")
    out_html = minify_html(raw)

    styles = _STYLE_ATTR_RE.findall(raw)
    dst = Path(out_path).expanduser() if out_path else src.with_suffix(".min.html")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out_html, encoding="utf-8")

    src_chars = len(raw)
    out_chars = len(out_html)
    saved = src_chars - out_chars
    return {
        "ok": True,
        "src_chars": src_chars,
        "out_chars": out_chars,
        "saved_chars": saved,
        "saved_pct": round((saved / src_chars * 100) if src_chars else 0.0, 2),
        "style_attrs": len(styles),
        "unique_styles": len({s for _, s in styles}),
        "wechat_limit": WECHAT_CONTENT_CHARS,
        "within_limit": out_chars <= WECHAT_CONTENT_CHARS,
        "output_file": str(dst.resolve()),
    }