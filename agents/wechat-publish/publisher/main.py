"""公众号SOP发布助手 — AiPy Python 工具型智能体服务入口。

符合《AiPy企业版智能体开发规范-V3.0》：
- Streamable HTTP Server（mcp + Starlette + uvicorn）
- 动态端口（port=0）
- STDOUT 单行 JSON 输出 {"type": "http_start", "port": N}
- Python 3.12，uv 管理依赖
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import socket
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

sys.path.insert(0, str(Path(__file__).parent))

from src.checker import check_text, sensitive_wordlist_stats
from src.parser import ParseResult, parse_document
from src.publisher import PublishError, publish_draft
from src.wechat_client import WeChatAPIError, WeChatClient
from src.wechat_compat import check_wechat_compat

# 日志一律走 STDERR，避免干扰 AiPy 从 STDOUT 读取端口信息（规范 4.4.2）
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wechat-sop-publish-assistant")

app = Server("wechat-sop-publish-assistant", version="0.4.0")

TOOL_PUBLISH = "publish_draft"
TOOL_CHECK = "check_text"
TOOL_STATS = "wordlist_stats"
TOOL_READ = "read_draft"
TOOL_COMPAT = "check_wechat_compat"

PUBLISH_SCHEMA = {
    "type": "object",
    "properties": {
        "html_path": {
            "type": "string",
            "description": "排版生成的公众号 HTML 文件的本地路径",
        },
        "title": {
            "type": "string",
            "description": "文章标题，不超过 32 字",
        },
        "cover_path": {
            "type": "string",
            "description": "封面图片本地路径（jpg/png，建议比例 2.35:1）",
        },
        "digest": {
            "type": "string",
            "description": "可选。文章摘要，不超过 120 字；留空则自动截取正文前 54 字",
        },
        "author": {
            "type": "string",
            "description": "可选。作者名，不超过 16 字",
        },
    },
    "required": ["html_path", "title", "cover_path"],
}

CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "html_path": {
            "type": "string",
            "description": "要校验的公众号 HTML 文件路径（与 text 二选一）",
        },
        "text": {
            "type": "string",
            "description": "要校验的纯文本内容（与 html_path 二选一）",
        },
    },
}

STATS_SCHEMA = {
    "type": "object",
    "properties": {},
}

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "终稿文件路径，支持 .docx / .md / .txt",
        },
    },
    "required": ["path"],
}

COMPAT_SCHEMA = {
    "type": "object",
    "properties": {
        "html_path": {
            "type": "string",
            "description": "要校验微信渲染兼容性的 HTML 文件路径",
        },
    },
    "required": ["html_path"],
}


def _get_client() -> WeChatClient:
    appid = os.environ.get("WECHAT_APPID", "")
    appsecret = os.environ.get("WECHAT_APPSECRET", "")
    if not appid or not appsecret:
        raise RuntimeError(
            "缺少公众号配置：请在 AiPy 智能体设置中填写 AppID / AppSecret（user_config）"
        )
    return WeChatClient(appid, appsecret)


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.ContentBlock]:
    try:
        if name == TOOL_PUBLISH:
            result = await asyncio.to_thread(
                _run_publish,
                html_path=arguments["html_path"],
                title=arguments["title"],
                cover_path=arguments["cover_path"],
                digest=arguments.get("digest", ""),
                author=arguments.get("author", ""),
            )
            return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

        if name == TOOL_CHECK:
            text = arguments.get("text", "")
            html_path = arguments.get("html_path", "")
            if not text and not html_path:
                return [types.TextContent(type="text", text="错误：html_path 与 text 至少提供一个。")]
            if not text:
                p = Path(html_path)
                if not p.is_file():
                    return [types.TextContent(type="text", text=f"错误：文件不存在：{html_path}")]
                text = p.read_text(encoding="utf-8")
            report = check_text(text)
            return [types.TextContent(type="text", text=report.summary())]

        if name == TOOL_STATS:
            return [types.TextContent(type="text", text=sensitive_wordlist_stats())]

        if name == TOOL_COMPAT:
            p = Path(arguments["html_path"])
            if not p.is_file():
                return [types.TextContent(type="text", text=f"错误：文件不存在：{arguments['html_path']}")]
            report = check_wechat_compat(p.read_text(encoding="utf-8"))
            payload = {
                "ok": report.ok,
                "errors": report.errors,
                "warnings": report.warnings,
                "summary": report.summary(),
            }
            return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]

        if name == TOOL_READ:
            result: ParseResult = parse_document(arguments["path"])
            payload = {
                "summary": result.summary(),
                "title": result.title,
                "source_type": result.source_type,
                "heading_count": result.heading_count,
                "image_paths": result.image_paths,
                "markdown": result.markdown,
            }
            return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

        return [types.TextContent(type="text", text=f"未知工具：{name}")]
    except (PublishError, WeChatAPIError, RuntimeError, ValueError, FileNotFoundError) as e:
        # 捕获业务异常返回友好信息，不让异常穿透到框架层（规范 4.2）
        return [types.TextContent(type="text", text=f"失败：{e}")]
    except Exception as e:
        logger.exception("工具执行异常")
        return [types.TextContent(type="text", text=f"工具执行异常：{type(e).__name__}: {e}")]


def _run_publish(html_path: str, title: str, cover_path: str, digest: str, author: str) -> dict:
    client = _get_client()
    return publish_draft(client, html_path, title, cover_path, digest, author)


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_PUBLISH,
            description=(
                "将排版好的公众号 HTML 导入微信公众号草稿箱："
                "先做微信渲染兼容性硬校验（样式必须内联，不允许 <style>/class/<script>），"
                "再自动上传正文图片到微信图床并回填 URL、上传封面、写入草稿。"
                "只写草稿箱，不做正式群发。需要已在智能体设置中配置 AppID/AppSecret，"
                "且本机出口 IP 已加入公众号后台 IP 白名单。"
                "注意：若 HTML 依赖 <style>/class，本工具会直接拒绝发布并说明修复方式。"
            ),
            inputSchema=PUBLISH_SCHEMA,
        ),
        types.Tool(
            name=TOOL_COMPAT,
            description=(
                "检查公众号 HTML 是否能在微信上正确渲染（样式必须全部内联）。"
                "可检出会导致「发布后格式全丢」的写法：<style> 标签、class 属性、"
                "<script>/<link>/<iframe>、伪元素（::before/::after）、:hover 等交互态、"
                "position:fixed/sticky、CSS 变量 var(--x)、@font-face。"
                "建议在排版完成后、发布之前先跑一次；publish_draft 也会强制执行同样的校验。"
            ),
            inputSchema=COMPAT_SCHEMA,
        ),
        types.Tool(
            name=TOOL_CHECK,
            description=(
                "对文章做文字层校验并输出报告：标点规范（半角/直引号）、"
                "品牌名（AiPY 大小写）、敏感词（广告法极限词/医疗功效/金融承诺/导流词）。"
                "敏感词库为内置词表，可通过设置 SENSITIVE_WORDLIST 环境变量挂载自定义词库 txt。"
                "视觉层问题（封面裁切、图片溢出等）需人工手机端预览确认。"
            ),
            inputSchema=CHECK_SCHEMA,
        ),
        types.Tool(
            name=TOOL_STATS,
            description="查看当前敏感词库装载情况（词条数量与类别），用于自检。",
            inputSchema=STATS_SCHEMA,
        ),
        types.Tool(
            name=TOOL_READ,
            description=(
                "读取终稿文件（Word .docx / Markdown .md / 纯文本 .txt）并转换成 Markdown。"
                "返回文章主标题、识别到的标题数量、抽取出的图片路径，以及 Markdown 正文。"
                "Word 文档的「标题 1/标题 2」样式会转成 # / ## 层级，"
                "内嵌图片抽取到同目录 images/ 并在文末以 ![](images/文件名) 引用。"
                "本工具通常作为排版第一步：先解析终稿，再把 Markdown 交给排版 skill 生成公众号 HTML。"
            ),
            inputSchema=READ_SCHEMA,
        ),
    ]


async def main() -> None:
    session_manager = StreamableHTTPSessionManager(app=app, json_response=True)

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            logger.info("wechat-sop-publish-assistant started")
            try:
                yield
            finally:
                logger.info("shutting down")

    starlette_app = Starlette(
        debug=False,
        routes=[Mount("/mcp", app=handle_streamable_http)],
        lifespan=lifespan,
    )
    starlette_app = CORSMiddleware(
        starlette_app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE"],
        expose_headers=["Mcp-Session-Id"],
    )

    import uvicorn

    config = uvicorn.Config(starlette_app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)

    original_startup = server.startup

    async def patched_startup(sockets: list[socket.socket] | None = None):
        await original_startup(sockets)
        for s in server.servers:
            for sock in s.sockets:
                # 规范 4.4.1/4.4.2：STDOUT 单行 JSON，flush 立即输出
                print(json.dumps({"type": "http_start", "port": sock.getsockname()[1]}), flush=True)
                return

    server.startup = patched_startup
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
