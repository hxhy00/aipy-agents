# -*- coding: utf-8 -*-
"""把 Markdown 代码块渲染成图片（微信公众号代码块方案 C）。

为什么用图片而不是 HTML：
    微信编辑器会折叠 HTML 源码里的换行符与连续空格，导致 <pre> 缩进丢失、
    长行被在字符中间硬折。用图片承载后，换行、缩进、语法高亮、长行的视觉呈现
    全部由浏览器排版引擎保证，微信无法篡改像素。

实现（不自己写高亮/折行算法，全用成熟库）：
    - 词法分析：Pygments PythonLexer
    - token → CSS class：Pygments HtmlFormatter（自带 .k/.s1/.c1/.nf … 映射）
    - 排版与折行：Playwright + Chromium（white-space:pre-wrap 处理长行）
    - 截图：device_scale_factor=2，视网膜屏清晰

用法：
    python code_image.py <markdown路径> <输出目录> [--cols N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer
from pygments import highlight as pyg_highlight

# ---------- 配色（深色主题，与原 HTML 一致）----------
BG = "#0F2233"
FG = "#D6E4F0"
BAR_BG = "#152C42"
DOTS = ("#FF5F57", "#FEBC2E", "#28C840")
CELL = 8.4                  # Menlo 13.5px 下单个半角字符宽度（实测）

# Pygments token class → 颜色（覆盖 PythonLexer 实际产出的全部 token）
TOKEN_COLORS = {
    # 关键字 / 命名空间 / 内置
    ".k": "#7FB3FF",   # Keyword (class, async, def, await, raise)
    ".kd": "#7FB3FF",  # Keyword.Declaration
    ".kn": "#7FB3FF",  # Keyword.Namespace (import/from)
    ".kc": "#7FB3FF",  # Keyword.Constant (True/False/None)
    ".nb": "#7FB3FF",  # Name.Builtin
    ".bp": "#7FB3FF",  # Name.Builtin.Pseudo (self)
    ".ow": "#7FB3FF",  # Operator.Word (and/or/not/in/is)
    # 名称
    ".n": FG,          # Name（普通标识符：context / my_agent …）← 之前漏掉导致看不清
    ".nc": "#FFD479",  # Name.Class
    ".nf": "#FFD479",  # Name.Function
    ".nd": "#C792EA",  # Name.Decorator
    ".na": "#8FD3F4",  # Name.Attribute
    ".nn": FG,         # Name.Namespace（模块路径 a2a.server…）
    ".nt": FG,         # Name.Tag
    # 字符串
    ".s": "#9BD98B", ".s1": "#9BD98B", ".s2": "#9BD98B",
    ".sb": "#9BD98B", ".se": "#9BD98B", ".sh": "#9BD98B",
    # 注释 / 数字 / 运算符 / 标点
    ".c": "#6B8CA8", ".c1": "#6B8CA8", ".cm": "#6B8CA8",
    ".m": "#FFAB70", ".mi": "#FFAB70", ".mf": "#FFAB70",
    ".o": "#A8C4DC",
    ".p": FG,          # Punctuation
}


def build_html(code: str, cols: int) -> str:
    """生成一个固定列宽的代码块 HTML，供 Chromium 截图。"""
    lexer = PythonLexer()
    formatter = HtmlFormatter(nowrap=True, cssclass="code")
    body = pyg_highlight(code.rstrip("\n"), lexer, formatter)

    color_css = "\n".join(f"pre.code {sel} {{ color: {col}; }}"
                          for sel, col in TOKEN_COLORS.items())
    # 强制深色背景，覆盖 Pygments 默认浅色主题的 .code / pre.code 底色
    bg_css = f".code, pre.code {{ background: {BG} !important; color: {FG}; }}"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
{formatter.get_style_defs(".code")}
{bg_css}
{color_css}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ background:{BG}; }}
.wrap {{
  width: {cols * CELL}px;
  background:{BG};
  font-family: Menlo, Monaco, "Noto Sans Mono CJK SC", monospace;
}}
.bar {{
  height: 30px;
  background:{BAR_BG};
  display:flex; align-items:center; gap:7px;
  padding-left:14px;
}}
.dot {{ width:11px; height:11px; border-radius:50%; }}
pre.code {{
  padding:14px 14px 16px;
  font-size:13.5px;
  line-height:1.62;
  color:{FG};
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  tab-size: 4;
}}
</style></head>
<body>
<div class="wrap">
  <div class="bar">
    <span class="dot" style="background:{DOTS[0]}"></span>
    <span class="dot" style="background:{DOTS[1]}"></span>
    <span class="dot" style="background:{DOTS[2]}"></span>
  </div>
  <pre class="code">{body}</pre>
</div>
</body></html>"""


# 测量用 JS：把 pre.code 内每个逻辑行（按 \n 切）单独包一层 div，
# 返回每个 div 的视觉行数（clientRect 数 > 1 即发生了折行）。
MEASURE_JS = """() => {
  const pre = document.querySelector('pre.code');
  // 取纯文本按换行切分，重建为每行一个块级 span 以测折行
  const text = pre.innerText;
  const lines = text.split('\\n');
  return lines.map(ln => {
    const s = document.createElement('span');
    s.style.whiteSpace = 'pre-wrap';
    s.style.display = 'block';
    s.textContent = ln || '\\u200b';
    pre.appendChild(s);
    const lh = parseFloat(getComputedStyle(pre).lineHeight) || 22;
    const h = s.getBoundingClientRect().height;
    s.remove();
    return Math.round(h / lh);
  });
}"""


def count_wrapped(page, code: str, cols: int) -> int:
    """在给定列宽下渲染代码块，返回发生折行的逻辑行数。"""
    page.set_content(build_html(code, cols), wait_until="load")
    counts = page.evaluate(MEASURE_JS)
    return sum(1 for c in counts if c > 1)


def extract_blocks(md_text: str) -> list[str]:
    """从 markdown 中抽取 ```python 代码块。"""
    blocks, lines, i = [], md_text.split("\n"), 0
    while i < len(lines):
        if lines[i].startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            blocks.append("\n".join(buf))
        i += 1
    return blocks


def render_all(md_path: Path, out_dir: Path, cols: int) -> list[Path]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    blocks = extract_blocks(md_path.read_text(encoding="utf-8"))
    print(f"找到 {len(blocks)} 个代码块，目标每行 ≤{cols} 半角字符")
    outs = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": int(cols * CELL) + 60, "height": 200},
            device_scale_factor=2)
        for idx, code in enumerate(blocks, 1):
            # 自动放宽列宽直到没有任何逻辑行折行（保证缩进不被软换行破坏）
            eff_cols = cols
            wrapped = count_wrapped(page, code, eff_cols)
            while wrapped > 0 and eff_cols < 72:
                eff_cols += 2
                wrapped = count_wrapped(page, code, eff_cols)
            html = build_html(code, eff_cols)
            page.set_content(html, wait_until="load")
            el = page.locator(".wrap")
            path = out_dir / f"code-{idx}.png"
            el.screenshot(path=str(path), type="png")
            info = page.evaluate(
                "() => { const w=document.querySelector('.wrap');"
                "return {w:w.offsetWidth,h:w.offsetHeight}; }")
            kb = path.stat().st_size / 1024
            flag = "" if wrapped == 0 else f"  ⚠️仍有{wrapped}行折行"
            print(f"  ✅ {path.name}  {info['w']}x{info['h']}  "
                  f"{kb:.0f} KB  (列宽={eff_cols}){flag}")
            outs.append(path)
        browser.close()
    return outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md_path")
    ap.add_argument("out_dir")
    ap.add_argument("--cols", type=int, default=52,
                    help="独占一行时每行最大半角字符数（默认 52）")
    args = ap.parse_args()
    render_all(Path(args.md_path), Path(args.out_dir), args.cols)


if __name__ == "__main__":
    main()
