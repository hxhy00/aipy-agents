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
import importlib
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
from src.resources import read_asset, read_reference, read_sop
from src.wechat_client import WeChatAPIError, WeChatClient
from src.wechat_compat import check_wechat_compat

# 日志一律走 STDERR，避免干扰 AiPy 从 STDOUT 读取端口信息（规范 4.4.2）
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wechat-sop-publish-assistant")

app = Server("wechat-sop-publish-assistant", version="2.0.1")

TOOL_PUBLISH = "publish_draft"
TOOL_CHECK = "check_text"
TOOL_STATS = "wordlist_stats"
TOOL_READ = "read_draft"
TOOL_COMPAT = "check_wechat_compat"

# 智能体自带的确定性能力（底层实现见 src/tools/）
TOOL_TEMPLATE_STYLE = "extract_template_style"
TOOL_VERIFY_HTML = "verify_html"
TOOL_VERIFY_FIDELITY = "verify_fidelity"
TOOL_MINIFY = "minify_inline_html"
TOOL_CODE_IMAGE = "render_code_images"

# 内置知识层读取（底层实现见 src/resources.py）
TOOL_SOP = "get_sop"
TOOL_REFERENCE = "get_reference"
TOOL_ASSET = "get_asset"

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

TEMPLATE_STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "用户提供的模板路径列表，可传多个。元素可以是文件，也可以是目录"
                "（目录会递归扫描，自动跳过隐藏目录与 node_modules）"
            ),
        },
    },
    "required": ["paths"],
}

VERIFY_HTML_SCHEMA = {
    "type": "object",
    "properties": {
        "html_path": {
            "type": "string",
            "description": "要预检的公众号 HTML 文件路径",
        },
        "title": {
            "type": "string",
            "description": "可选。拟用标题，用于一并校验 ≤32 字限制",
        },
        "digest": {
            "type": "string",
            "description": "可选。拟用摘要，用于一并校验 ≤120 字限制",
        },
        "author": {
            "type": "string",
            "description": "可选。拟用作者，用于一并校验 ≤16 字限制",
        },
    },
    "required": ["html_path"],
}

VERIFY_FIDELITY_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "源终稿文件路径（.docx / .md / .txt），即 read_draft 的输入那个文件",
        },
        "html": {
            "type": "string",
            "description": "排版后的公众号 HTML 文件路径",
        },
        "main_title": {
            "type": "string",
            "description": (
                "可选。文章主标题。按规则主标题默认不进正文，所以不计入缺失；"
                "留空时自动从源文档推断"
            ),
        },
    },
    "required": ["source", "html"],
}

MINIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "html_path": {
            "type": "string",
            "description": "待压缩的公众号 HTML 文件路径",
        },
        "out_path": {
            "type": "string",
            "description": (
                "可选。压缩产物输出路径；留空则写到 <输入文件名>.min.html，返回值里的 "
                "output_file 会给出绝对路径"
            ),
        },
    },
    "required": ["html_path"],
}

CODE_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "md_path": {
            "type": "string",
            "description": "含围栏代码块（``` 或 ~~~）的 Markdown 文件路径",
        },
        "out_dir": {
            "type": "string",
            "description": "PNG 输出目录，不存在会自动创建",
        },
        "cols": {
            "type": "integer",
            "minimum": 20,
            "maximum": 200,
            "description": (
                "可选。每行最多多少个半角字符（CJK 按 2 列计），默认 52。"
                "超宽行会在源码层折行，避免微信在屏宽处把代码拦腰截断"
            ),
        },
        "style": {
            "type": "string",
            "description": "可选。Pygments 配色风格名，默认 monokai（深色）",
        },
        "font_size": {
            "type": "integer",
            "minimum": 8,
            "maximum": 40,
            "description": "可选。字号，默认 15",
        },
        "line_numbers": {
            "type": "boolean",
            "description": "可选。是否画行号栏，默认 false（公众号读者一般不需要）",
        },
    },
    "required": ["md_path", "out_dir"],
}

SOP_SCHEMA = {
    "type": "object",
    "properties": {
        "section": {
            "type": "string",
            "description": (
                "可选。章节名或关键词，按 Markdown 二级/三级标题匹配"
                "（如「步骤 4」「硬规则」「资产使用」）；留空返回全文。"
                "匹配不到时会返回全部可用章节名"
            ),
        },
    },
}

REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": (
                "参考规范文件名，带不带 .md 后缀都行，如 style_matrix、"
                "wechat_layout_rules、content_fidelity_rules。"
                "只接受内置文件名，不接受路径"
            ),
        },
    },
    "required": ["name"],
}

ASSET_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "description": (
                "素材类目名，如 style_examples / color_palettes / icons / dividers / "
                "card_patterns。只接受内置类目名，不接受路径"
            ),
        },
        "name": {
            "type": "string",
            "description": (
                "可选。类目下的文件名（如 technology.html、palettes.json）；"
                "留空则返回该类目的文件清单"
            ),
        },
    },
    "required": ["category"],
}


# 缺依赖时统一回给模型的话术。模型读到「重新安装本智能体」就知道该把问题
# 反馈给用户，而不是反复重试或改用别的方式硬凑。
_DEPENDENCY_HINT = (
    "该能力的依赖未在本智能体环境中安装，功能不可用。"
    "请提示用户重新安装/升级本智能体后重试，不要用其他方式绕过。"
)


class _ToolDependencyError(RuntimeError):
    """src/tools 下某能力模块或其第三方依赖不可用。

    message 已经是可直接回给模型的完整中文提示，调用方不要再包装一层。
    """


def _load_tool(module: str, attr: str):
    """延迟导入 src.tools 下的能力模块并取出目标函数。

    为什么必须在函数内导入：
        src/tools/code_image.py 依赖 pygments 与 Pillow，这两个包可能没装
        （老版本智能体、或按需安装的场景）。若在模块顶层导入，一旦缺依赖就会
        ImportError 让整个 server 起不来，连累其余 12 个工具全部不可用。
        函数内导入把失败范围收敛到「这一个工具」，其余工具照常可用——
        与 src/tools/verify_fidelity.py 处理 python-docx、
        src/parser.py 处理 docx 子模块的延迟导入做法一致。

    缺依赖时抛 _ToolDependencyError（而不是 RuntimeError）：
        单独一个异常类型才能保证「缺依赖」不会被误判——工具自己抛的
        RuntimeError（比如参数问题）不该被当成依赖缺失上报给用户。
    """
    try:
        return getattr(importlib.import_module(f"src.tools.{module}"), attr)
    except Exception as e:  # noqa: BLE001 —— ImportError/AttributeError/模块内其他异常都要兜住
        logger.warning("加载能力模块失败 src.tools.%s.%s：%s", module, attr, e)
        raise _ToolDependencyError(
            f"{_DEPENDENCY_HINT}（原始错误：{type(e).__name__}: {e}）"
        ) from e


def _dependency_missing(e: Exception) -> dict:
    """缺依赖时的统一失败结构，字段与各工具的返回 schema 保持一致。

    直接用异常消息，不再二次包装——_load_tool 已经拼好了完整提示，
    再包一层会出现同一句话嵌套两遍的脏文案。
    """
    message = str(e)
    return {
        "ok": False,
        "error": message,
        "errors": [message],
        "dependency_missing": True,
        "hint": "该能力对应 src/tools 下依赖第三方库的能力模块。",
    }


def _get_client() -> WeChatClient:
    appid = os.environ.get("WECHAT_APPID", "")
    appsecret = os.environ.get("WECHAT_APPSECRET", "")
    if not appid or not appsecret:
        raise RuntimeError(
            "缺少公众号配置：请在 AiPy 智能体设置中填写 AppID / AppSecret（user_config）"
        )
    return WeChatClient(appid, appsecret)


def _json_text(payload: dict[str, Any]) -> types.TextContent:
    """统一把 dict 结果转成 TextContent，序列化风格与既有工具保持一致。"""
    return types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))


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

        # ---------- 以下为智能体自带的确定性能力 ----------
        # 统一走 _load_tool 延迟导入 + asyncio.to_thread 执行：
        # 缺依赖时只让这一个工具报错，不影响 server 启动与其他工具。

        if name == TOOL_TEMPLATE_STYLE:
            try:
                fn = _load_tool("template_style", "extract_template_style")
            except _ToolDependencyError as e:
                return [_json_text(_dependency_missing(e))]
            paths = arguments.get("paths") or []
            if not isinstance(paths, list) or not paths:
                return [_json_text({"ok": False, "error": "paths 必须是非空的模板路径列表"})]
            out = await asyncio.to_thread(fn, paths=[str(p) for p in paths])
            return [_json_text(out)]

        if name == TOOL_VERIFY_HTML:
            try:
                fn = _load_tool("html_verify", "verify_html")
            except _ToolDependencyError as e:
                return [_json_text(_dependency_missing(e))]
            out = await asyncio.to_thread(
                fn,
                html_path=arguments["html_path"],
                title=arguments.get("title", ""),
                digest=arguments.get("digest", ""),
                author=arguments.get("author", ""),
            )
            return [_json_text(out)]

        if name == TOOL_VERIFY_FIDELITY:
            try:
                fn = _load_tool("verify_fidelity", "verify_fidelity")
            except _ToolDependencyError as e:
                return [_json_text(_dependency_missing(e))]
            out = await asyncio.to_thread(
                fn,
                source=arguments["source"],
                html=arguments["html"],
                main_title=arguments.get("main_title", ""),
            )
            return [_json_text(out)]

        if name == TOOL_MINIFY:
            try:
                fn = _load_tool("minify", "minify_inline_html")
            except _ToolDependencyError as e:
                return [_json_text(_dependency_missing(e))]
            out = await asyncio.to_thread(
                fn,
                html_path=arguments["html_path"],
                out_path=arguments.get("out_path", ""),
            )
            return [_json_text(out)]

        if name == TOOL_CODE_IMAGE:
            try:
                render_fn = _load_tool("code_image", "render_code_images")
                font_fn = _load_tool("code_image_font", "resolve_code_font")
            except _ToolDependencyError as e:
                return [_json_text(_dependency_missing(e))]

            # 出图前先探一次字体：系统只有 Menlo/Consolas 这类纯 ASCII 字体时，
            # 代码块里的中文注释会渲染成空白（豆腐块），读者看到的是「注释凭空消失」。
            # 这个代价必须让模型知道，而不是等图片出来才发现。
            try:
                font_path, font_note = await asyncio.to_thread(font_fn)
            except Exception as e:  # noqa: BLE001 —— 字体探测失败不应阻断出图
                logger.warning("代码字体探测失败：%s", e)
                font_path, font_note = None, f"代码字体探测失败（{type(e).__name__}: {e}），中文可能显示异常。"

            out = await asyncio.to_thread(
                render_fn,
                md_path=arguments["md_path"],
                out_dir=arguments["out_dir"],
                cols=int(arguments.get("cols", 52)),
                style=str(arguments.get("style") or "monokai"),
                font_size=int(arguments.get("font_size", 15)),
                line_numbers=bool(arguments.get("line_numbers", False)),
            )

            if font_path is None and font_note:
                # render_code_images 内部也会把同一条说明写进 warnings，
                # 这里只在还没写进去时补一条，避免同一句话在返回里重复两遍。
                warnings = list(out.get("warnings") or [])
                if not any(font_note in w for w in warnings):
                    warnings.insert(0, font_note)
                out["warnings"] = warnings
            return [_json_text(out)]

        # ---------- 以下为内置知识层读取 ----------

        if name == TOOL_SOP:
            return [_json_text(read_sop(arguments.get("section", "")))]

        if name == TOOL_REFERENCE:
            return [_json_text(read_reference(arguments.get("name", "")))]

        if name == TOOL_ASSET:
            return [_json_text(read_asset(arguments.get("category", ""), arguments.get("name", "")))]

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
                "本工具通常作为排版第一步：先解析终稿，再调用 get_sop 获取排版规则，按规则生成公众号 HTML。"
            ),
            inputSchema=READ_SCHEMA,
        ),
        types.Tool(
            name=TOOL_SOP,
            description=(
                "读取本智能体的排版全流程 SOP。**任何公众号排版任务开始之前，先调一次不带 section 的 "
                "get_sop 拿全流程规则**；只想拿某一步细则时用 section 按章节取（如「步骤 4」「硬规则」）。"
                "它是这套能力的唤起入口，覆盖：公众号文章SOP、公众号排版、公众号美化、公众号视觉设计、"
                "生成公众号HTML、Word转公众号、企业宣传推文、活动推文、产品发布、公众号模板或风格学习、"
                "终稿到草稿箱全流程、docx转公众号、文章解析与发布、从Word到公众号草稿箱。"
                "文档里列出的每一步（read_draft / extract_template_style / verify_html / "
                "check_wechat_compat / verify_fidelity / minify_inline_html / render_code_images / "
                "publish_draft）都是本智能体直接提供的工具，**你直接调用即可，不要用 shell 去跑任何脚本**。"
            ),
            inputSchema=SOP_SCHEMA,
        ),
        types.Tool(
            name=TOOL_REFERENCE,
            description=(
                "读取单篇排版规范文档，写 HTML 之前需要精确规则时调用，不要用 shell 去读这些文件。"
                "按需取用：style_matrix（用户没给模板路径时按主题选风格）、"
                "style_learning_rules（用户给了模板路径时的原创化/融合规则）、"
                "design_principles、wechat_layout_rules（微信移动端版式与内联样式硬规则）、"
                "content_fidelity_rules（正文保真 100%）、image_preservation_rules、"
                "title_navigation_rules（章节导航只能逐字复制原二级标题）、"
                "visual_elements_library、code_block_rules、quality_check（四重自检清单）。"
                "name 只传文件名（带不带 .md 后缀都行）；匹配不到时会回带全部可用文件名。"
            ),
            inputSchema=REFERENCE_SCHEMA,
        ),
        types.Tool(
            name=TOOL_ASSET,
            description=(
                "读取视觉素材库里的可复用片段源码（HTML/SVG/JSON），设计排版需要具体卡片、分割线、"
                "图标或配色数据时调用，不要用 shell 去读这些文件。类目："
                "style_examples（完整视觉语言示例，只学结构不照抄）、"
                "color_palettes（name=palettes.json，角色化配色数据）、"
                "icons（可内联的原创几何图标）、dividers（微信兼容分割组件）、"
                "card_patterns（标题/导航/引用/重点/图片/数据/CTA 卡片）。"
                "不给 name 时返回该类目文件清单。取到片段后必须把占位文字替换成本篇原文；"
                "不适用就不用该组件，不要为了凑视觉元素数量硬塞。"
            ),
            inputSchema=ASSET_SCHEMA,
        ),
        types.Tool(
            name=TOOL_TEMPLATE_STYLE,
            description=(
                "从用户提供的模板路径抽取结构化设计参数（配色、字号、行高、圆角、阴影、渐变、标题骨架、"
                "卡片与分割线特征），供你原创化融合。**当用户明确给了参考模板/案例/截图目录时调用**"
                "（公众号模板或风格学习、按模板排版、学一下这个排版风格）；"
                "用户没给模板路径就不要调——那时应改用 get_reference(name=\"style_matrix\") 按主题选风格。"
                "本工具只做「抽取」不做「套用」，模板不内置；返回 ok=false 说明路径无效或抽不到特征，"
                "此时**不要臆造模板特征**，按 fallback 里给的路径走。"
            ),
            inputSchema=TEMPLATE_STYLE_SCHEMA,
        ),
        types.Tool(
            name=TOOL_VERIFY_HTML,
            description=(
                "公众号 HTML 发布可行性预检（体积/图片/字段），是三重预检的第 1 步。"
                "排版完成、准备发布前必须先调一次：它检出的是「发布时才会失败」的问题——"
                "base64 内嵌图片（src=\"data:...\"）、外链图片（微信会过滤成空白）、"
                "本地图片文件不存在、\\uXXXX 未解码转义、正文超 2 万字符或 1MB、"
                "标题/摘要/作者超长。返回 ok=false 必须先修复再调 publish_draft；"
                "正文超限时用 minify_inline_html 做无损压缩，**不要把样式挪进 <style> 来凑体积**。"
                "注意它只管「发布会不会失败」，不管「发布后好不好看」——后者由 "
                "check_wechat_compat 与 verify_fidelity 负责。"
            ),
            inputSchema=VERIFY_HTML_SCHEMA,
        ),
        types.Tool(
            name=TOOL_VERIFY_FIDELITY,
            description=(
                "内容保真反向核验，三重预检的第 3 步，发布前最后一道关卡。"
                "正文保真 100% 是不可突破的底线，而人工（或你）逐段目检一定会漏——"
                "真实踩过的坑是排版时漏掉了文章开头的两段导语。本工具逐段比对源文档与排版 HTML，"
                "检出缺失段落、多出段落、错序段落、数字不一致。**当 verify_html 与 check_wechat_compat "
                "都通过后调用**；返回 ok=false 时按 missing/extra 列表逐条补回或删改，"
                "补到 fidelity_pct=100 才允许调用 publish_draft。"
            ),
            inputSchema=VERIFY_FIDELITY_SCHEMA,
        ),
        types.Tool(
            name=TOOL_MINIFY,
            description=(
                "内联样式 HTML 无损压缩，用来解决微信正文 2 万字符 / 1MB 硬限制。"
                "只做视觉等价的字符级压缩（CSS 声明压缩、颜色缩写、标签间空白折叠、去注释），"
                "**绝不引入 <style>/class、绝不删改正文内容**——这正是它与「手工挤内容」和"
                "「把样式挪进 <style>」的本质区别，后两者分别会丢内容和导致草稿箱格式全丢。"
                "仅当 verify_html 报「正文超限」时调用；压缩后要再跑一次 check_wechat_compat 与 "
                "verify_fidelity，确认没有引入 style/class 且内容仍 100% 保真。"
            ),
            inputSchema=MINIFY_SCHEMA,
        ),
        types.Tool(
            name=TOOL_CODE_IMAGE,
            description=(
                "把 Markdown 里的围栏代码块（``` 或 ~~~）渲染成微信安全的 PNG 图片。"
                "**文章里有代码块时调用**——微信编辑器会折叠 HTML 源码里的换行与连续空格，"
                "导致 <pre> 缩进丢失、长行被从字符中间硬折，文字代码块在公众号必然破版；"
                "用图片承载后，换行、缩进、语法高亮、长行的视觉呈现全部由像素保证，微信无法篡改。"
                "每个代码块产出一张 PNG，返回值里的 path 是可直接当本地图片引用的绝对路径。"
                "超宽行会在源码层按 cols 折行（无法断行的长 URL/base64 会被强制切断并在 warnings 告警），"
                "所以微信屏宽处不会再拦腰截断代码。源文是 .docx 时先用 read_draft 拿到 Markdown 再传 md_path。"
            ),
            inputSchema=CODE_IMAGE_SCHEMA,
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
