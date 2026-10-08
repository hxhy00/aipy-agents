"""微信渲染兼容性硬校验（发布前强制关卡）。

为什么必须放在服务端：
    客户端预检只能提示、不能拦截，而且历史上它**放行过**带 <style>/class 的 HTML，
    导致「预检通过 → 发布成功 → 草稿箱格式全丢」。这种错误的代价极高
    （用户以为好了，实际要重发），所以必须由发布服务端兜底：
    只要 HTML 依赖微信会剥离的样式承载方式，直接拒绝写入草稿箱。

判定为阻断项（error）：
    - <style> 标签（微信整体剥离）
    - class 属性（微信剥离，样式无处附着）
    - <script>/<link>/<iframe>/<video>/<audio>/<canvas>/<form>/<input>/<button> 等被过滤标签
    - 伪元素/交互态承载装饰（::before/::after/:hover 等）
    - position:fixed / sticky
    - CSS 变量 var(--x)
    - 外链字体 @font-face
    - white-space:nowrap 且没有配套 overflow 处理（375px 屏宽下横向溢出）
    - 完全没有 style 属性（说明样式根本没内联）

判定为提示项（warning）：
    - <pre> 文本代码块（微信折叠空白 + 字符中间硬折，应改成代码图片）
    - word-break:break-all（任意字符断行，破坏代码/英文换行结构）
    - overflow:auto/scroll（手机端横向滚动体验差）
    - 内联样式重复度过高（可用无损压缩回收体积）
    - 关键信息只靠渐变表达（渐变被过滤后层级丢失）

本模块不依赖 bs4，保持轻量，避免与 checker.py 的解析路径耦合。
所有定位信息都带行号/序号，便于模型直接跳到出问题的地方改。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# 微信会整体剥离或直接过滤的标签
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

# 内联 style 属性里的可疑写法
PSEUDO_RE = re.compile(r"::?(before|after|hover|focus|active|visited|first-child|last-child|nth-child)\b", re.IGNORECASE)
FIXED_POS_RE = re.compile(r"position\s*:\s*(fixed|sticky)", re.IGNORECASE)
VAR_RE = re.compile(r"var\s*\(\s*--")
FONTFACE_RE = re.compile(r"@font-face", re.IGNORECASE)
NOWRAP_RE = re.compile(r"white-space\s*:\s*nowrap", re.IGNORECASE)
OVERFLOW_RE = re.compile(r"overflow(-x)?\s*:\s*(auto|scroll)", re.IGNORECASE)
BREAK_ALL_RE = re.compile(r"word-break\s*:\s*break-all", re.IGNORECASE)

_STYLE_ATTR_RE = re.compile(r'\sstyle\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_CLASS_ATTR_RE = re.compile(r'\sclass\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)

# 同一份内联样式重复多少处才提示压缩（给个阈值，避免小 HTML 误报）
_DUP_STYLE_THRESHOLD = 5


@dataclass
class CompatReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        if self.ok:
            head = "微信渲染兼容性校验通过：样式已全部内联。"
        else:
            head = (
                f"微信渲染兼容性校验未通过（{len(self.errors)} 项阻断）：\n"
                "以下写法会被微信静默剥离，发布后草稿箱会丢失格式，请先修复："
            )
        lines = [head]
        for i, e in enumerate(self.errors, 1):
            lines.append(f"  {i}. {e}")
        for w in self.warnings:
            lines.append(f"  [提示] {w}")
        return "\n".join(lines)


def _find_tag(html: str, tag: str) -> list[int]:
    """返回某个标签出现的行号列表（1-based）。"""
    return [
        i
        for i, line in enumerate(html.splitlines(), 1)
        if re.search(rf"<\s*{tag}\b", line, re.IGNORECASE)
    ]


def _fmt_lines(lines: list[int]) -> str:
    """把行号列表格式化成「第 3、7 行（共 12 处）」。"""
    shown = "、".join(str(n) for n in lines[:5])
    more = f"（共 {len(lines)} 处）" if len(lines) > 5 else ""
    return f"第 {shown} 行{more}"


def _top_class_names(matches: list[str]) -> str:
    """class 值里的 Top5 类名，用于告诉模型该改哪几处。"""
    names: Counter[str] = Counter()
    for m in matches:
        names.update(n for n in m.split() if n)
    return "、".join(f".{n}" for n, _ in names.most_common(5))


def check_wechat_compat(html: str) -> CompatReport:
    """检查 HTML 是否可被微信正确渲染（样式必须内联）。

    入参是 HTML 字符串（不是文件路径），返回 CompatReport。
    """
    rep = CompatReport()

    # ---------- 1. 会被微信剥离/过滤的标签（带行号定位） ----------
    for tag, reason in FORBIDDEN_TAGS.items():
        lines = _find_tag(html, tag)
        if lines:
            rep.errors.append(f"发现 <{tag}> 标签（{_fmt_lines(lines)}）：{reason}")

    # ---------- 2. class 属性 ----------
    class_matches = _CLASS_ATTR_RE.findall(html)
    if class_matches:
        rep.errors.append(
            f"发现 {len(class_matches)} 处 class 属性（如 {_top_class_names(class_matches)}）："
            f"微信草稿 API 会剥离 class，样式会全部丢失。请改用内联 style 属性。"
        )

    # ---------- 3. 内联样式里的不兼容写法 ----------
    styles = _STYLE_ATTR_RE.findall(html)

    if not styles:
        rep.errors.append(
            "整个 HTML 没有任何 style 属性——样式很可能写在 <style> 或 class 里，"
            "微信不会保留。请把样式全部内联到标签的 style 属性上。"
        )

    for i, css in enumerate(styles, 1):
        if FIXED_POS_RE.search(css):
            rep.errors.append(f"第 {i} 处内联样式使用 position:fixed/sticky，微信移动端会降级为普通流布局")
        if VAR_RE.search(css):
            rep.errors.append(f"第 {i} 处内联样式使用 CSS 变量 var(--…)，微信不解析变量，取不到值")
        if PSEUDO_RE.search(css):
            rep.errors.append(
                f"第 {i} 处内联样式依赖伪元素/交互态（before/after/hover 等），"
                f"微信静态渲染不生效；装饰请用实体空元素 + 边框/色块实现"
            )

    if FONTFACE_RE.search(html):
        rep.errors.append("@font-face 外链字体不被微信支持，请改用系统字体栈")

    # ---------- 4. 横向滚动 ----------
    nowrap_count = sum(1 for c in styles if NOWRAP_RE.search(c))
    ovf_count = sum(1 for c in styles if OVERFLOW_RE.search(c))
    if nowrap_count and not ovf_count:
        rep.errors.append(
            f"有 {nowrap_count} 处 white-space:nowrap 但没有配套 overflow 处理，"
            f"长文本在 375px 宽度下会横向溢出"
        )
    elif ovf_count:
        rep.warnings.append(f"使用了 {ovf_count} 处 overflow:auto/scroll，手机端横向滚动体验差，建议改为换行或卡片化")

    # ---------- 5. 文本代码块（应改成代码图片） ----------
    # 微信会折叠源码空白并在字符中间硬折长行，文本代码块在手机上必然缩进丢失/换行错乱。
    pre_lines = _find_tag(html, "pre")
    if pre_lines:
        rep.warnings.append(
            f"发现 {len(pre_lines)} 处 <pre> 文本代码块（{_fmt_lines(pre_lines)}）："
            f"微信会折叠空白并在字符中间硬折长行，缩进与换行必然错乱。"
            f"请改用 render_code_images 渲染成图片后以 <img> 引用"
        )
    if BREAK_ALL_RE.search(html):
        rep.warnings.append(
            "发现 word-break:break-all（任意字符断行），会破坏代码/英文的换行结构，"
            "建议移除并从源码层拆分长行"
        )

    # ---------- 6. 重复样式提示（体积优化线索） ----------
    dup = 0
    if styles:
        counter = Counter(styles)
        dup = sum(c - 1 for c in counter.values() if c > 1)
        if dup >= _DUP_STYLE_THRESHOLD:
            rep.warnings.append(
                f"内联样式存在 {dup} 处重复，可运行 minify_inline_html 无损压缩体积"
                f"（当前 HTML {len(html)} 字符）"
            )

    # ---------- 7. 关键信息不可只靠渐变/阴影表达 ----------
    grad = sum(1 for c in styles if "gradient" in c.lower())
    if grad:
        rep.warnings.append(
            f"有 {grad} 处使用渐变（linear-gradient/radial-gradient）。"
            f"微信可能过滤渐变，请确认被过滤后标题/卡片仍靠底色、边框、留白保持层级。"
        )

    rep.stats = {
        "html_chars": len(html),
        "style_attrs": len(styles),
        "class_attrs": len(class_matches),
        "duplicate_styles": dup,
        "has_style_tag": bool(_find_tag(html, "style")),
        "top_classes": _top_class_names(class_matches),
    }
    return rep