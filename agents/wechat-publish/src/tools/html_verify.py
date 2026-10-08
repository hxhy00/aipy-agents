"""排版产物发布前预检（在调用 publish_draft 之前先把「一定会失败」的问题查出来）。

为什么需要这一步：
    这些问题如果不预检，会在发布时才由微信 API 报错，白白浪费一轮往返
    （图片上传、封面上传、草稿写入都是不可逆的外部调用）。

检查项：
    1. HTML 文件存在且为 UTF-8
    2. 无 base64 内嵌图片（src="data:..."）——微信图床上传不支持，必须改本地路径
    3. 无外部 http(s) 图片（微信会过滤成空白，必须改为本地文件）
    4. 所有本地 <img src> 文件真实存在
    5. 无 \\uXXXX 形式的未解码转义（排版产物应为真实中文字符）
    6. 标题/摘要/作者字数符合微信限制
    7. 正文体积 ≤ 2 万字符且 < 1MB

模块名说明：
    函数叫 verify_html，模块名刻意避开同名（html_verify），
    避免与包内其他命名混淆，也避免和「校验微信兼容性」的职责混淆——
    本模块只管「发布会不会失败」，不管「渲染会不会变形」。

依赖：仅标准库。
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

MAX_TITLE_LEN = 32
MAX_AUTHOR_LEN = 16
MAX_DIGEST_LEN = 120
MAX_CONTENT_CHARS = 20000
MAX_CONTENT_BYTES = 1024 * 1024
MMBIZ_HOST = "mmbiz.qpic.cn"

_IMG_SRC_RE = re.compile(r'<img[^>]*\ssrc\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def verify_html(html_path: str, title: str = "", digest: str = "", author: str = "") -> dict:
    """预检公众号 HTML，返回 {ok, errors, warnings, stats}。

    ok=False 表示存在阻断问题，**必须先修复再调用 publish_draft**。
    """
    errors: list[str] = []
    warnings: list[str] = []

    p = Path(html_path).expanduser()
    if not p.is_file():
        return {
            "ok": False,
            "errors": [f"HTML 文件不存在：{html_path}"],
            "warnings": [],
            "stats": {},
        }

    try:
        html = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {
            "ok": False,
            "errors": ["HTML 不是 UTF-8 编码，请另存为 UTF-8 后重试"],
            "warnings": [],
            "stats": {},
        }

    # 1. 转义残留
    if re.search(r"\\u[0-9a-fA-F]{4}", html):
        errors.append(
            "HTML 中存在 \\uXXXX 形式的未解码转义序列（中文被转义），"
            "请确保排版产物以 ensure_ascii=False 输出 UTF-8 中文。"
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