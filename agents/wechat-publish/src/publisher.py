"""publish_draft 业务逻辑：微信兼容性硬校验、图片中转回填、字段/体积校验、入草稿箱。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .wechat_client import WeChatClient
from .wechat_compat import check_wechat_compat

# 官方硬限制
MAX_TITLE_LEN = 32
MAX_AUTHOR_LEN = 16
MAX_DIGEST_LEN = 120
MAX_CONTENT_CHARS = 20000
MAX_CONTENT_BYTES = 1024 * 1024

MMBIZ_HOST = "mmbiz.qpic.cn"


class PublishError(Exception):
    """发布流程中的业务错误（带用户可读信息）。"""


def _validate_fields(title: str, author: str, digest: str) -> None:
    if len(title) > MAX_TITLE_LEN:
        raise PublishError(f"标题超长：{len(title)} 字 > {MAX_TITLE_LEN} 字，请修改后重试")
    if author and len(author) > MAX_AUTHOR_LEN:
        raise PublishError(f"作者名超长：{len(author)} 字 > {MAX_AUTHOR_LEN} 字")
    if digest and len(digest) > MAX_DIGEST_LEN:
        raise PublishError(f"摘要超长：{len(digest)} 字 > {MAX_DIGEST_LEN} 字")


def _migrate_images(html: str, html_dir: Path, client: WeChatClient) -> tuple[str, int]:
    """把 HTML 中本地 <img> 的 src 替换为微信图床 URL。

    - 本地存在的路径（绝对或相对 HTML 所在目录）→ uploadimg 上传后回填
    - 已是 mmbiz.qpic.cn 的跳过
    - 其他外部 URL → 报错（微信会将其过滤为空白，必须中转）
    """
    soup = BeautifulSoup(html, "html.parser")
    migrated = 0
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            raise PublishError("HTML 中存在空的 <img src>，请先修复排版输出")
        if MMBIZ_HOST in urlparse(src).netloc:
            continue
        if src.startswith("data:"):
            raise PublishError(
                "HTML 中图片使用了 base64 内嵌（src=\"data:image/...\"），无法上传。\n"
                "请把图片保存为本地文件，并把 <img src> 改为本地文件路径"
                "（如 images/xxx.png），再重新发布。"
            )

        candidate = Path(src)
        if not candidate.is_absolute():
            candidate = (html_dir / src).resolve()
        if candidate.is_file():
            url = client.upload_content_image(candidate)
            img["src"] = url
            migrated += 1
        else:
            raise PublishError(
                f"图片不存在或为外部 URL（微信会过滤外部图片导致空白）：{src}\n"
                f"请确保图片文件在本地且路径正确，或已使用微信图床 URL。"
            )
    return str(soup), migrated


def _validate_content_size(content: str) -> None:
    encoded = content.encode("utf-8")
    if len(content) > MAX_CONTENT_CHARS:
        raise PublishError(
            f"正文超限：{len(content)} 字符 > {MAX_CONTENT_CHARS} 字符，"
            f"请精简排版（如减少内联 CSS 重复）"
        )
    if len(encoded) > MAX_CONTENT_BYTES:
        raise PublishError(
            f"正文超限：{len(encoded) / 1024:.0f}KB > 1MB，请精简排版"
        )


def publish_draft(
    client: WeChatClient,
    html_path: str,
    title: str,
    cover_path: str,
    digest: str = "",
    author: str = "",
) -> dict:
    """完整发布链路：图片中转 → 封面 → 草稿箱。返回结果摘要。"""
    html_file = Path(html_path)
    cover_file = Path(cover_path)
    if not html_file.is_file():
        raise PublishError(f"HTML 文件不存在：{html_path}")
    if not cover_file.is_file():
        raise PublishError(f"封面文件不存在：{cover_path}")

    _validate_fields(title, author, digest)

    html = html_file.read_text(encoding="utf-8")

    # 微信渲染兼容性硬校验：必须先于图片上传，避免白白消耗上传配额
    compat = check_wechat_compat(html)
    if not compat.ok:
        raise PublishError(
            "发布被拦截：HTML 使用了微信会剥离的样式写法，直接发布会导致草稿箱格式丢失。\n"
            + compat.summary()
            + "\n修复方式：把所有样式改为标签上的内联 style 属性，"
            "移除 <style>/class/<script>，装饰改用实体元素（边框、色块、空 span）。"
        )

    content, migrated = _migrate_images(html, html_file.parent, client)
    _validate_content_size(content)

    thumb_media_id = client.upload_cover(cover_file)

    article: dict = {
        "title": title,
        "content": content,
        "thumb_media_id": thumb_media_id,
    }
    if author:
        article["author"] = author
    if digest:
        article["digest"] = digest

    media_id = client.add_draft([article])
    return {
        "media_id": media_id,
        "migrated_images": migrated,
        "content_chars": len(content),
        "message": "已写入公众号草稿箱，请在公众平台后台「草稿箱」查看并人工预览确认（本工具不做正式群发）。",
    }
