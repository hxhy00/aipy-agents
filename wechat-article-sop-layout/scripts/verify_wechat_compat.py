#!/usr/bin/env python3
"""微信公众号渲染兼容性预检（全流程 SOP 第 4 步的强制关卡）。

为什么需要这个脚本：
    `verify_html.py` 检查的是「发布会不会失败」（图片、体积、转义、字段长度）。
    但微信草稿 API 在写入时还有一层**静默重写**：它会剥离 <style> 标签、class 属性、
    伪元素承载的装饰、position:fixed 等，且不报错。
    结果是「预检通过 → 发布成功 → 用户打开草稿箱发现格式全丢」，
    这种返工最伤用户，必须在本地拦住。

检查项（阻断）：
    1. <style> 标签 —— 微信会整体剥离，样式全丢
    2. class 属性 —— 微信会剥离，无法关联样式
    3. <script> / <link> / <iframe> / <video> / <audio> / <canvas> —— 微信直接过滤
    4. 伪元素承载的装饰（CSS 中出现 ::before / ::after / :hover / :focus 等）
    5. position: fixed / sticky —— 移动端阅读场景微信会降级
    6. CSS 变量 var(--x) —— 微信不解析，取不到值
    7. 外链字体 @font-face —— 微信不支持
    8. 横向滚动（white-space:nowrap 且未配 overflow）与复杂 flex 嵌套

检查项（警告）：
    - <pre> 文本代码块（微信折叠空白 + 字符中间硬折，应转图片，见 code_block_rules.md）
    - word-break:break-all（任意字符断行，破坏代码/英文换行结构）
    - 关键信息只靠渐变/阴影表达（被过滤后层级丢失）
    - 内联样式重复度高（提示用 minify_inline_html.py 压缩）

用法：
    python scripts/verify_wechat_compat.py <html路径> [--json]

退出码：0 = 无阻断项；1 = 存在阻断项
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# 微信会整体剥离的标签
FORBIDDEN_TAGS = {
    "style": "微信草稿 API 会整体剥离 <style>，其中的样式全部失效——所有样式必须内联到 style 属性",
    "script": "微信直接过滤 <script>",
    "link": "微信过滤 <link>（外链样式表/字体不可用）",
    "iframe": "微信过滤 <iframe>",
    "video": "微信过滤 <video>（只能用腾讯视频组件）",
    "audio": "微信过滤 <audio>",
    "canvas": "微信过滤 <canvas>",
    "form": "微信过滤 <form> 及表单控件",
    "input": "微信过滤表单控件",
    "button": "微信过滤 <button>，按钮需用 <span>/<a> 加内联样式实现",
}

# CSS 中出现即视为问题的模式（伪元素/交互态无法在微信静态渲染中生效）
PSEUDO_RE = re.compile(r"::?(before|after|hover|focus|active|visited|first-child|last-child|nth-child)\b", re.IGNORECASE)

# 内联 style 属性里的可疑写法
FIXED_POS_RE = re.compile(r"position\s*:\s*(fixed|sticky)", re.IGNORECASE)
VAR_RE = re.compile(r"var\s*\(\s*--")
FONTFACE_RE = re.compile(r"@font-face", re.IGNORECASE)
NOWRAP_RE = re.compile(r"white-space\s*:\s*nowrap", re.IGNORECASE)
OVERFLOW_RE = re.compile(r"overflow(-x)?\s*:\s*(auto|scroll)", re.IGNORECASE)
BREAK_ALL_RE = re.compile(r"word-break\s*:\s*break-all", re.IGNORECASE)

_STYLE_ATTR_RE = re.compile(r'\sstyle\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_CLASS_ATTR_RE = re.compile(r'\sclass\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _find_tag(html: str, tag: str) -> list[int]:
    """返回某个标签出现的行号列表（1-based）。"""
    lines = []
    for i, line in enumerate(html.splitlines(), 1):
        if re.search(rf"<\s*{tag}\b", line, re.IGNORECASE):
            lines.append(i)
    return lines


def verify(html_path: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    p = Path(html_path).expanduser()
    if not p.is_file():
        return {"ok": False, "errors": [f"HTML 文件不存在：{html_path}"], "warnings": []}

    html = p.read_text(encoding="utf-8")

    # ---------- 1. 会被微信剥离/过滤的标签 ----------
    for tag, reason in FORBIDDEN_TAGS.items():
        lines = _find_tag(html, tag)
        if lines:
            shown = "、".join(str(n) for n in lines[:5])
            more = f"（共 {len(lines)} 处）" if len(lines) > 5 else ""
            errors.append(f"发现 <{tag}> 标签（第 {shown} 行{more}）：{reason}")

    # ---------- 2. class 属性 ----------
    class_matches = _CLASS_ATTR_RE.findall(html)
    if class_matches:
        names = Counter()
        for m in class_matches:
            for n in m.split():
                names[n] += 1
        top = "、".join(f".{n}" for n, _ in names.most_common(5))
        errors.append(
            f"发现 {len(class_matches)} 处 class 属性（如 {top}）："
            f"微信草稿 API 会剥离 class，样式会全部丢失。请改用内联 style 属性。"
        )

    # ---------- 3. 内联样式里的不兼容写法 ----------
    styles = _STYLE_ATTR_RE.findall(html)

    if not styles:
        warnings.append(
            "整个 HTML 没有任何 style 属性——如果正文确实需要排版，"
            "很可能是样式写在了 <style> 或 class 里，微信不会保留。"
        )

    for i, css in enumerate(styles, 1):
        if FIXED_POS_RE.search(css):
            errors.append(f"第 {i} 处内联样式使用 position:fixed/sticky，微信移动端会降级为普通流布局")
        if VAR_RE.search(css):
            errors.append(f"第 {i} 处内联样式使用 CSS 变量 var(--…)，微信不解析变量，取不到值")
        if PSEUDO_RE.search(css):
            errors.append(
                f"第 {i} 处内联样式依赖伪元素/交互态（before/after/hover 等），"
                f"微信静态渲染不生效；装饰请用实体空元素 + 边框/色块实现"
            )

    if FONTFACE_RE.search(html):
        errors.append("@font-face 外链字体不被微信支持，请改用系统字体栈")

    # ---------- 4. 横向滚动 ----------
    nowrap_count = sum(1 for c in styles if NOWRAP_RE.search(c))
    ovf_count = sum(1 for c in styles if OVERFLOW_RE.search(c))
    if nowrap_count and not ovf_count:
        errors.append(
            f"有 {nowrap_count} 处 white-space:nowrap 但没有配套 overflow 处理，"
            f"长文本在 375px 宽度下会横向溢出"
        )
    elif ovf_count:
        warnings.append(f"使用了 {ovf_count} 处 overflow:auto/scroll，手机端横向滚动体验差，建议改为换行或卡片化")

    # ---------- 4.5 文本代码块（应转图片） ----------
    # 微信会折叠源码空白并在字符中间硬折长行，文本代码块在手机上必然缩进丢失/换行错乱。
    # 详见 references/code_block_rules.md；正确做法是 scripts/code_image.py 渲染成图片。
    pre_count = len(_find_tag(html, "pre"))
    if pre_count:
        warnings.append(
            f"发现 {pre_count} 处 <pre> 文本代码块：微信会折叠空白并在字符中间硬折长行，"
            f"缩进与换行必然错乱。请改用 scripts/code_image.py 渲染成图片后以 <img> 引用"
            f"（参见 references/code_block_rules.md）"
        )
    if BREAK_ALL_RE.search(html):
        warnings.append(
            "发现 word-break:break-all（任意字符断行），会破坏代码/英文的换行结构，"
            "建议移除并从源码层拆分长行"
        )

    # ---------- 5. 重复样式提示（体积优化线索） ----------
    if styles:
        counter = Counter(styles)
        dup = sum(c - 1 for c in counter.values() if c > 1)
        if dup:
            warnings.append(
                f"内联样式存在 {dup} 处重复，可运行 minify_inline_html.py 无损压缩体积"
                f"（当前 HTML {len(html)} 字符）"
            )

    # ---------- 6. 关键信息不可只靠渐变/阴影 ----------
    grad = sum(1 for c in styles if "gradient" in c.lower())
    if grad:
        warnings.append(
            f"有 {grad} 处使用渐变（linear-gradient/radial-gradient）。"
            f"微信可能过滤渐变，请确认被过滤后标题/卡片仍靠底色、边框、留白保持层级。"
        )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "html_chars": len(html),
            "style_attrs": len(styles),
            "class_attrs": len(class_matches),
            "has_style_tag": bool(re.search(r"<\s*style\b", html, re.IGNORECASE)),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号 HTML 微信渲染兼容性预检")
    ap.add_argument("html_path", help="待检查的 HTML 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（默认也是 JSON）")
    args = ap.parse_args()

    result = verify(args.html_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
