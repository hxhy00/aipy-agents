"""代码块配图的字体解析：挑一个「能渲染中文」的等宽/近似等宽字体文件。

为什么需要这个模块：
    排版里代码块最终渲染成 PNG。macOS 的 Menlo、Windows 的 Consola、
    Linux 的 DejaVu Sans Mono 都是纯 ASCII 字体，**没有任何 CJK 字形**——
    中文注释会被渲染成空白（豆腐块），读者看到的是「注释消失了」。
    而中文字体（苹方/宋体/雅黑/思源黑体）大多不是等宽，但代码块必须对齐，
    只能退而求其次用「近似等宽 + 可渲染中文」。

策略（按优先级）：
    1. 优先挑**能渲染中文**的候选字体（等宽性次之，因为可读性优先）；
    2. 找不到中文字体时，退回纯 ASCII 等宽字体，并在说明里明确告知
       「中文注释会显示为空白」；
    3. 一个候选都探不到时返回 None，由调用方回退到 Pygments 内置默认字体，
       同时必须在 warnings 里提示用户安装思源黑体 / Noto Sans CJK。

已知坑（真实遇到，不是防御性冗余）：
    - Pillow 对部分 TTC（字体集合）支持有限，加载时会抛 OSError /
      InvalidArgument，所以每个候选都必须**实际加载探测**后再采用；
    - Pygments 的 ImageFormatter 只有在 `os.path.isfile(font_name)` 为真时
      才把 font_name 当文件路径处理，否则会当成字体**名称**去系统里查，
      查不到直接抛 FontNotFound。所以这里必须保证返回值是真实存在的文件。

依赖：仅 Pillow（fontTools 若已安装则优先用它查 cmap，更准；没有也能工作）。
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

# 候选字体按优先级排列：(路径模板, 是否要求支持中文)
# macOS 的 PingFang.ttc 并非所有系统版本都有（新版已挪到
# /System/Library/Fonts/PingFang.ttc 之外的私有目录），所以必须逐个探测。
_CANDIDATES: dict[str, list[tuple[str, bool]]] = {
    "darwin": [
        ("/System/Library/Fonts/PingFang.ttc", True),
        ("/System/Library/Fonts/Supplemental/Songti.ttc", True),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", True),
        ("/Library/Fonts/Arial Unicode.ttf", True),
        ("/System/Library/Fonts/Menlo.ttc", False),
    ],
    "win32": [
        ("C:/Windows/Fonts/msyh.ttc", True),
        ("C:/Windows/Fonts/simsun.ttc", True),
        ("C:/Windows/Fonts/consola.ttf", False),
    ],
    "linux": [
        ("/usr/share/fonts/**/NotoSansCJK*.ttc", True),
        ("/usr/share/fonts/**/wqy-microhei.ttc", True),
        ("/usr/share/fonts/**/wqy-zenhei.ttc", True),
        ("/usr/share/fonts/**/DejaVuSansMono.ttf", False),
    ],
}

# 用于探测 CJK 覆盖的码位：U+4E2D「中」，以及一个私用区码位（字体必然缺失）
_PROBE_CJK = "中"
_PROBE_MISSING = "\ue123"

_NO_CJK_HINT = (
    "当前系统没有找到任何可渲染中文的等宽字体，代码块里的中文注释会显示为空白。"
    "建议安装思源黑体 / Noto Sans CJK（Linux: apt install fonts-noto-cjk；"
    "macOS 自带 PingFang 或 Hiragino Sans GB；Windows 自带微软雅黑）。"
)


def _platform_key() -> str:
    """把 sys.platform 归一成候选表里的键。"""
    if sys.platform.startswith("darwin"):
        return "darwin"
    if sys.platform.startswith("win"):
        return "win32"
    return "linux"


def _expand_candidates() -> list[tuple[str, bool]]:
    """把候选模板展开成真实存在的文件列表（Linux 的 ** 通配用 glob 处理）。"""
    out: list[tuple[str, bool]] = []
    for pattern, needs_cjk in _CANDIDATES[_platform_key()]:
        if "**" in pattern:
            # recursive=True 才会展开 **；排序保证结果稳定可复现
            for hit in sorted(glob.glob(pattern, recursive=True)):
                if os.path.isfile(hit):
                    out.append((hit, needs_cjk))
        elif os.path.isfile(pattern):
            out.append((pattern, needs_cjk))
    return out


def _pil_can_load(path: str) -> bool:
    """Pillow 能否加载该字体文件（TTC 支持有限，加载失败要能继续试下一个）。"""
    try:
        from PIL import ImageFont

        ImageFont.truetype(path, 14)
        return True
    except Exception:  # noqa: BLE001 —— OSError / InvalidArgument / SyntaxError 等一律视为不可用
        return False


def font_supports_cjk(path: str) -> bool:
    """检查字体文件的 cmap 里是否覆盖中文字形。

    优先用 fontTools（直接读 cmap，最准）；没装 fontTools 时退回 Pillow 的
    字形渲染对比法：把「中」和一个私用区码位（字体必然没有的字形）分别渲染，
    两者像素完全一致就说明「中」其实也缺字形。

    返回 False 时**不代表字体文件坏了**，只代表它渲染不出中文。
    """
    if not path or not os.path.isfile(path):
        return False

    try:
        from fontTools.ttLib import TTCollection, TTFont

        if path.lower().endswith(".ttc"):
            # TTC 是字体集合，取第一个子字体即可判断覆盖情况
            fonts = TTCollection(path, lazy=True).fonts
        else:
            fonts = [TTFont(path, fontNumber=0, lazy=True)]
        for font in fonts:
            if 0x4E2D in (font.getBestCmap() or {}):
                return True
        return False
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 —— 字体损坏/TTC 不受支持等，退回渲染法
        pass

    try:
        from PIL import ImageFont

        font = ImageFont.truetype(path, 20)
        rendered_cjk = bytes(font.getmask(_PROBE_CJK, mode="L"))
        rendered_missing = bytes(font.getmask(_PROBE_MISSING, mode="L"))
    except Exception:  # noqa: BLE001
        return False

    # 缺字形时两者都渲染成同一个 .notdef（多为空白），像素完全一致
    return rendered_cjk != rendered_missing


def resolve_code_font() -> tuple[str | None, str]:
    """解析出当前平台可用的代码块字体文件路径。

    返回 (字体路径 或 None, 说明文字)。说明文字是给模型读的，要能直接
    据此判断「中文能不能正常显示」，不能只说「成功/失败」。

    调用方拿到 None 时应回退到系统默认字体，并**必须**把本函数返回的说明
    原样透出到 warnings 里，不要静默失败。
    """
    candidates = _expand_candidates()
    if not candidates:
        return None, _NO_CJK_HINT

    ascii_fallback: str | None = None

    for path, needs_cjk in candidates:
        if not _pil_can_load(path):
            # Pillow 打不开（常见于 TTC），继续试下一个，不中断整条链子
            continue
        if needs_cjk:
            if font_supports_cjk(path):
                return path, f"已选用可渲染中文的代码字体：{path}"
            # 文件能用但没有中文字形，当作 ASCII 回退的候选继续找
            ascii_fallback = ascii_fallback or path
            continue
        ascii_fallback = ascii_fallback or path

    if ascii_fallback:
        return ascii_fallback, (
            f"已选用代码字体：{ascii_fallback}。"
            "注意：该字体没有中文字形，代码块中的中文注释会显示为空白，"
            "建议安装思源黑体 / Noto Sans CJK 后重试，或把注释改为英文。"
        )

    return None, _NO_CJK_HINT


def code_font_candidates() -> list[str]:
    """返回当前平台探测到的全部候选路径（诊断用，模型排查字体问题时用）。"""
    return [p for p, _ in _expand_candidates()]


def _self_check() -> dict:
    """自检入口：python -m src.tools.code_image_font —— 打印字体解析结果。"""
    path, note = resolve_code_font()
    return {
        "font_path": path,
        "note": note,
        "supports_cjk": font_supports_cjk(path) if path else False,
        "candidates": code_font_candidates(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(_self_check(), ensure_ascii=False, indent=2))