"""微信渲染兼容性硬校验（发布前强制关卡）。

为什么必须放在服务端：
    `verify_html.py` 是客户端预检，只能提示、不能拦截，而且历史上它**放行过**
    带 <style>/class 的 HTML，导致「预检通过 → 发布成功 → 草稿箱格式全丢」。
    这种错误的代价极高（用户以为好了，实际要重发），所以必须由发布服务端兜底：
    只要 HTML 依赖微信会剥离的样式承载方式，直接拒绝写入草稿箱。

判定为阻断项：
    - <style> 标签（微信整体剥离）
    - class 属性（微信剥离，样式无处附着）
    - <script> / <link> / <iframe> 等被过滤标签
    - 伪元素/交互态承载装饰
    - position:fixed / sticky
    - CSS 变量 var(--x)
    - 完全没有 style 属性（说明样式根本没内联）

本模块不依赖 bs4，保持轻量，避免与 checker.py 的解析路径耦合。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FORBIDDEN_TAGS = {
    "style": "微信草稿 API 会整体剥离 <style>，其中的样式全部失效",
    "script": "微信直接过滤 <script>",
    "link": "微信过滤 <link>（外链样式表/字体不可用）",
    "iframe": "微信过滤 <iframe>",
    "video": "微信过滤 <video>",
    "canvas": "微信过滤 <canvas>",
    "form": "微信过滤 <form> 及表单控件",
    "input": "微信过滤表单控件",
    "button": "微信过滤 <button>",
}

_PSEUDO_RE = re.compile(r"::?(before|after|hover|focus|active|visited|first-child|last-child|nth-child)\b", re.IGNORECASE)
_FIXED_RE = re.compile(r"position\s*:\s*(fixed|sticky)", re.IGNORECASE)
_VAR_RE = re.compile(r"var\s*\(\s*--")
_FONTFACE_RE = re.compile(r"@font-face", re.IGNORECASE)
_CLASS_RE = re.compile(r"\sclass\s*=", re.IGNORECASE)
_STYLE_RE = re.compile(r'\sstyle\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


@dataclass
class CompatReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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


def check_wechat_compat(html: str) -> CompatReport:
    """检查 HTML 是否可被微信正确渲染（样式必须内联）。"""
    rep = CompatReport()

    for tag, reason in FORBIDDEN_TAGS.items():
        if re.search(rf"<\s*{tag}\b", html, re.IGNORECASE):
            rep.errors.append(f"发现 <{tag}> 标签：{reason}")

    if _CLASS_RE.search(html):
        n = len(_CLASS_RE.findall(html))
        rep.errors.append(
            f"发现 {n} 处 class 属性：微信会剥离 class，样式将全部丢失，请改用内联 style 属性"
        )

    styles = _STYLE_RE.findall(html)
    if not styles:
        rep.errors.append(
            "HTML 中没有任何内联 style 属性：样式很可能写在 <style> 或 class 里，微信不会保留"
        )

    for i, css in enumerate(styles, 1):
        if _FIXED_RE.search(css):
            rep.errors.append(f"第 {i} 处内联样式使用 position:fixed/sticky，微信移动端会降级")
        if _VAR_RE.search(css):
            rep.errors.append(f"第 {i} 处内联样式使用 CSS 变量 var(--…)，微信不解析变量")
        if _PSEUDO_RE.search(css):
            rep.errors.append(
                f"第 {i} 处内联样式依赖伪元素/交互态（before/after/hover 等），微信不生效"
            )

    if _FONTFACE_RE.search(html):
        rep.errors.append("@font-face 外链字体不被微信支持")

    grad = sum(1 for c in styles if "gradient" in c.lower())
    if grad:
        rep.warnings.append(
            f"有 {grad} 处渐变样式；微信可能过滤渐变，请确认过滤后层级仍成立"
        )

    return rep
