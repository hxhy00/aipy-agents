#!/usr/bin/env python3
"""排版产物发布前预检（全流程 SOP 第 4 步之前的确定性检查）。

用途：
    在调用智能体 `publish_draft` 之前，先本地把这些「一定会导致发布失败」的问题查出来。
    这些问题如果不预检，会在发布时才由微信 API 报错，浪费一轮往返。

检查项：
    1. HTML 文件存在且为 UTF-8
    2. 无 base64 内嵌图片（src="data:..."）——微信图床上传不支持，必须改本地路径
    3. 无外部 http(s) 图片（微信会过滤成空白，必须改为本地文件）
    4. 所有本地 <img src> 文件真实存在
    5. 无 \\uXXXX 形式的未解码转义（排版产物应为真实中文字符）
    6. 标题/摘要/作者字数符合微信限制
    7. 正文体积 ≤ 2 万字符且 < 1MB

用法：
    python scripts/verify_html.py <html路径> [--title "标题"] [--digest "摘要"] [--author "作者"]

退出码：0 = 全部通过；1 = 存在阻断问题
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

MAX_TITLE_LEN = 32
MAX_AUTHOR_LEN = 16
MAX_DIGEST_LEN = 120
MAX_CONTENT_CHARS = 20000
MAX_CONTENT_BYTES = 1024 * 1024
MMBIZ_HOST = "mmbiz.qpic.cn"

_IMG_SRC_RE = re.compile(r'<img[^>]*\ssrc\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def verify(html_path: str, title: str, digest: str, author: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    p = Path(html_path).expanduser()
    if not p.is_file():
        return {"ok": False, "errors": [f"HTML 文件不存在：{html_path}"], "warnings": []}

    try:
        html = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "errors": ["HTML 不是 UTF-8 编码，请另存为 UTF-8 后重试"], "warnings": []}

    # 1. 转义残留
    if re.search(r"\\u[0-9a-fA-F]{4}", html):
        errors.append(
            "HTML 中存在 \\uXXXX 形式的未解码转义序列（中文被转义），"
            "请确保排版脚本以 ensure_ascii=False 输出 UTF-8 中文。"
        )

    # 2. 图片检查
    srcs = _IMG_SRC_RE.findall(html)
    if not srcs:
        warnings.append("正文中未发现任何 <img> 图片。")

    base64_imgs = [s for s in srcs if s.strip().startswith("data:")]
    external_imgs = [
        s for s in srcs
        if s.strip().startswith(("http://", "https://")) and MMBIZ_HOST not in urlparse(s.strip()).netloc
    ]
    local_imgs = [s for s in srcs if not s.strip().startswith(("data:", "http://", "https://"))]

    if base64_imgs:
        errors.append(
            f"发现 {len(base64_imgs)} 张 base64 内嵌图片（src=\"data:image/...\"）。"
            "微信图床不支持 base64，请把图片存为本地文件并改为本地路径引用。"
        )
    if external_imgs:
        errors.append(
            f"发现 {len(external_imgs)} 张外部图片链接，微信会过滤为空白："
            + "；".join(external_imgs[:3])
            + "。请下载到本地后改为本地路径。"
        )

    missing = []
    for s in local_imgs:
        candidate = Path(s.strip())
        if not candidate.is_absolute():
            candidate = (p.parent / s.strip()).resolve()
        if not candidate.is_file():
            missing.append(s.strip())
    if missing:
        errors.append(
            f"以下本地图片文件不存在（{len(missing)} 张）：" + "；".join(missing[:5])
        )

    # 3. 字段长度
    if title and len(title) > MAX_TITLE_LEN:
        errors.append(f"标题超长：{len(title)} > {MAX_TITLE_LEN} 字")
    if digest and len(digest) > MAX_DIGEST_LEN:
        errors.append(f"摘要超长：{len(digest)} > {MAX_DIGEST_LEN} 字")
    if author and len(author) > MAX_AUTHOR_LEN:
        errors.append(f"作者超长：{len(author)} > {MAX_AUTHOR_LEN} 字")

    # 4. 体积
    encoded = html.encode("utf-8")
    if len(html) > MAX_CONTENT_CHARS:
        errors.append(f"正文超限：{len(html)} 字符 > {MAX_CONTENT_CHARS} 字符")
    if len(encoded) > MAX_CONTENT_BYTES:
        errors.append(f"正文超限：{len(encoded) / 1024:.0f}KB > 1MB")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "html_chars": len(html),
            "html_kb": round(len(encoded) / 1024, 1),
            "images_total": len(srcs),
            "images_local": len(local_imgs),
            "images_base64": len(base64_imgs),
            "images_external": len(external_imgs),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号 HTML 发布前预检")
    ap.add_argument("html_path", help="待发布的 HTML 文件路径")
    ap.add_argument("--title", default="", help="文章标题（用于长度校验）")
    ap.add_argument("--digest", default="", help="文章摘要（用于长度校验）")
    ap.add_argument("--author", default="", help="作者名（用于长度校验）")
    args = ap.parse_args()

    result = verify(args.html_path, args.title, args.digest, args.author)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
