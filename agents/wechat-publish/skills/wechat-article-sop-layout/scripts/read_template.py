#!/usr/bin/env python3
"""模板路径抽取脚本：把用户当次提供的「模板路径」抽成结构化设计参数。

全流程 SOP 的第 2 步（确定性环节）。本 skill **不内置模板**：
模板只能由用户通过路径提供，本脚本只做「抽取」，不做「套用」。

用法：
    python scripts/read_template.py <模板路径> [<模板路径2> ...] [--json]

支持的路径：
    - 单个文件或目录（目录会递归扫描，跳过隐藏目录与 node_modules）
    - .html/.htm  ：抽取内联样式、配色、字号、标题骨架、卡片/分割线特征
    - .md/.txt    ：抽取标题骨架与文字排版线索
    - .json       ：按配色/参数类 JSON 抽取色值与数值
    - .png/.jpg/.jpeg/.webp ：记录为图片类模板（需 AI 读图提炼，脚本只登记）

输出：
    stdout 打印 JSON（ok / templates / merged / errors / warnings）
    --json 时忽略，始终输出 JSON。

依赖：仅标准库。图片类模板由 AI 读图完成抽取。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_TEXT_SUFFIXES = {".html", ".htm", ".md", ".markdown", ".txt"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_JSON_SUFFIXES = {".json"}
_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".idea", ".vscode"}
_MAX_BYTES = 2 * 1024 * 1024  # 单个模板文件上限，超过则跳过

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB_RE = re.compile(r"rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}[^)]*\)", re.IGNORECASE)
_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([\d.]+)\s*(px|em|rem|pt)", re.IGNORECASE)
_LINE_HEIGHT_RE = re.compile(r"line-height\s*:\s*([\d.]+)\s*(px|em|rem|%)?", re.IGNORECASE)
_SPACING_RE = re.compile(r"(?:margin|padding)(?:-(?:top|bottom|left|right))?\s*:\s*([^;\"]+)", re.IGNORECASE)
_MAX_WIDTH_RE = re.compile(r"(?:max-)?width\s*:\s*([\d.]+)\s*(px|%)", re.IGNORECASE)
_BORDER_RADIUS_RE = re.compile(r"border-radius\s*:\s*([^;\"]+)", re.IGNORECASE)
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;\"]+)", re.IGNORECASE)
_GRADIENT_RE = re.compile(r"(linear|radial)-gradient\([^)]*\)", re.IGNORECASE)
_SHADOW_RE = re.compile(r"box-shadow\s*:\s*([^;\"]+)", re.IGNORECASE)
_TAG_STYLE_RE = re.compile(r"<([a-zA-Z][\w-]*)([^>]*?)style\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)
_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_HTML_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_TEXT_RE = re.compile(r"<[^>]+>")


def _norm_hex(value: str) -> str:
    """把 #abc 归一化为 #aabbcc，统一小写。"""
    v = value.lower()
    if len(v) == 4:
        return "#" + "".join(c * 2 for c in v[1:])
    return v


def _strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", _TEXT_RE.sub("", html)).strip()


def _collect_declarations(css: str) -> dict[str, list[str]]:
    """从 CSS 片段中提取关注的声明值。"""
    return {
        "colors": [_norm_hex(c) for c in _HEX_RE.findall(css)] + _RGB_RE.findall(css),
        "font_sizes": [f"{n}{u}" for n, u in _FONT_SIZE_RE.findall(css)],
        "line_heights": [
            (f"{n}{u}" if u else n) for n, u in _LINE_HEIGHT_RE.findall(css)
        ],
        "spacing": [s.strip() for s in _SPACING_RE.findall(css)],
        "widths": [f"{n}{u}" for n, u in _MAX_WIDTH_RE.findall(css)],
        "radii": [r.strip() for r in _BORDER_RADIUS_RE.findall(css)],
        "fonts": [f.strip() for f in _FONT_FAMILY_RE.findall(css)],
        "gradients": _GRADIENT_RE.findall(css),
        "shadows": [s.strip() for s in _SHADOW_RE.findall(css)],
    }


def _extract_html(raw: str) -> dict:
    css_parts = _STYLE_BLOCK_RE.findall(raw)
    inline_styles = [m[2] for m in _TAG_STYLE_RE.findall(raw)]
    css = "\n".join(css_parts + inline_styles)
    decl = _collect_declarations(css)

    heading_tags = Counter(int(m[0]) for m in _HTML_HEADING_RE.findall(raw))
    heading_samples = [
        {"level": int(lv), "text": _strip_tags(body)[:60]}
        for lv, body in _HTML_HEADING_RE.findall(raw)
    ][:12]

    # 用出现次数最多的色值猜测角色（仅作候选，最终由 AI 判断）
    top_colors = [c for c, _ in Counter(decl["colors"]).most_common(8)]

    return {
        "kind": "html",
        "has_style_block": bool(css_parts),
        "inline_style_count": len(inline_styles),
        "colors": top_colors,
        "font_sizes": decl["font_sizes"][:10],
        "line_heights": decl["line_heights"][:10],
        "widths": decl["widths"][:6],
        "border_radii": decl["radii"][:6],
        "font_families": decl["fonts"][:5],
        "gradients": decl["gradients"][:5],
        "box_shadows": decl["shadows"][:5],
        "heading_counts": {f"h{k}": v for k, v in sorted(heading_tags.items())},
        "heading_samples": heading_samples,
        "has_card_like": bool(re.search(r"border|background|border-radius", css, re.IGNORECASE)),
        "has_divider": bool(
            re.search(r"<hr|border-(?:top|bottom)|divider|分割", raw, re.IGNORECASE)
        ),
    }


def _extract_markdown(raw: str) -> dict:
    headings = _MD_HEADING_RE.findall(raw)
    return {
        "kind": "markdown",
        "heading_counts": {f"h{len(h)}": 1 for h, _ in headings},
        "heading_samples": [
            {"level": len(h), "text": t.strip()[:60]} for h, t in headings
        ][:12],
        "hint": "Markdown 模板只能提供标题骨架与文字节奏，配色/卡片需由 AI 依据文字描述判断。",
    }


def _extract_json(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"kind": "json", "parse_error": str(e)}

    found_colors: list[str] = []
    found_numbers: list[str] = []

    def walk(node, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str):
                    if _HEX_RE.fullmatch(v.strip()):
                        found_colors.append(_norm_hex(v.strip()))
                    elif re.fullmatch(r"[\d.]+(px|em|rem|%)?", v.strip()):
                        found_numbers.append(f"{k}={v.strip()}")
                else:
                    walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)

    walk(data)
    return {
        "kind": "json",
        "colors": found_colors[:20],
        "numbers": found_numbers[:20],
        "top_level_keys": list(data.keys())[:15] if isinstance(data, dict) else [],
    }


def _extract_image(path: Path) -> dict:
    size = path.stat().st_size
    return {
        "kind": "image",
        "path": str(path),
        "bytes": size,
        "hint": "图片类模板：请用读图能力提炼配色、标题骨架、卡片形态、图片处理与留白节奏，不要复刻 Logo 或整版结构。",
    }


def _extract_one(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return {"path": str(path), **_extract_image(path)}
    if path.stat().st_size > _MAX_BYTES:
        raise ValueError(f"文件超过 {_MAX_BYTES // 1024 // 1024}MB，已跳过：{path}")
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if suffix in {".html", ".htm"}:
        return {"path": str(path), **_extract_html(raw)}
    if suffix in {".md", ".markdown", ".txt"}:
        return {"path": str(path), **_extract_markdown(raw)}
    if suffix in _JSON_SUFFIXES:
        return {"path": str(path), **_extract_json(raw)}
    raise ValueError(f"不支持的模板格式：{suffix}")


def _iter_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        files: list[Path] = []
        for child in sorted(target.rglob("*")):
            if any(part in _SKIP_DIRS for part in child.parts):
                continue
            if child.is_file() and (
                child.suffix.lower() in _TEXT_SUFFIXES
                | _IMAGE_SUFFIXES
                | _JSON_SUFFIXES
            ):
                files.append(child)
        return files
    raise FileNotFoundError(f"路径不存在：{target}")


def _merge(templates: list[dict]) -> dict:
    """跨模板聚合：共同点作为统一基础，供 AI 做 Style Fusion。"""
    colors: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for t in templates:
        colors.update(t.get("colors") or [])
        sizes.update(t.get("font_sizes") or [])
    return {
        "template_count": len(templates),
        "kinds": sorted({t.get("kind", "") for t in templates}),
        "common_colors": [c for c, _ in colors.most_common(10)],
        "common_font_sizes": [s for s, _ in sizes.most_common(8)],
        "has_image_template": any(t.get("kind") == "image" for t in templates),
        "hint": (
            "多模板融合：共同点作统一基础，选一个主导风格占 70–80%，"
            "其余每个只贡献一个不冲突特征；单篇最多两种视觉语言。"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="模板路径抽取：用户提供的模板 → 结构化设计参数（不内置模板）"
    )
    ap.add_argument("paths", nargs="+", help="模板路径（文件或目录，可多个）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（默认也是 JSON）")
    args = ap.parse_args()

    templates: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []

    for raw_path in args.paths:
        target = Path(raw_path).expanduser()
        try:
            files = _iter_files(target)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")
            continue
        if not files:
            warnings.append(f"目录内未找到可识别的模板文件：{raw_path}")
            continue
        for f in files:
            try:
                templates.append(_extract_one(f))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{f} → {type(e).__name__}: {e}")

    if not templates:
        payload = {
            "ok": False,
            "error": "未能从给定路径抽取到任何模板特征；请检查路径或文件格式",
            "errors": errors,
            "warnings": warnings,
            "fallback": "references/style_matrix.md",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    if any(t.get("kind") == "image" for t in templates):
        warnings.append("包含图片类模板，需由 AI 读图完成配色与版式提炼后再融合。")

    payload = {
        "ok": True,
        "templates": templates,
        "merged": _merge(templates),
        "errors": errors,
        "warnings": warnings,
        "next_step": (
            "按 references/style_learning_rules.md 做原创化融合：保留 2–3 个抽象原则，"
            "至少改变两项（标题骨架/导航方式/卡片形态/分割线/图片框/留白节奏/强调方式）。"
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
