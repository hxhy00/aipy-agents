import asyncio
import contextlib
import json
import logging
import os
import socket
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import mcp.types as types
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.server.lowlevel import Server
from mcp.shared._httpx_utils import McpHttpClientFactory
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)


def _no_verify_http_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """跳过 SSL 证书校验的 httpx 客户端工厂（用于自签发证书环境）。"""
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout or httpx.Timeout(30.0),
        auth=auth,
        verify=False,
        follow_redirects=True,
    )


# ── 环境变量配置 ────────────────────────────────────────────────────────────────
ENDPOINT = os.getenv("ZOOMEYE_BE_ENDPOINT", "").rstrip("/")
USERNAME = os.getenv("ZOOMEYE_BE_USERNAME", "")
PASSWORD = os.getenv("ZOOMEYE_BE_PASSWORD", "")

if not ENDPOINT:
    logger.warning("ZOOMEYE_BE_ENDPOINT 未设置，服务将无法连接到上游 MCP 服务器")
if not USERNAME or not PASSWORD:
    logger.warning("ZOOMEYE_BE_USERNAME / ZOOMEYE_BE_PASSWORD 未设置")

# MCP token 本地缓存路径（与 main.py 同目录）
_TOKEN_FILE = Path(__file__).parent / "jwt_token"

# ── 上游连接状态 ────────────────────────────────────────────────────────────────
_upstream_session: ClientSession | None = None
_upstream_tools: list[types.Tool] = []


def _read_cached_token() -> str | None:
    """从本地文件读取缓存的 MCP token，文件不存在或为空时返回 None。"""
    try:
        token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        return token or None
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"读取缓存 token 失败: {e}")
        return None


def _save_token(token: str) -> None:
    """将 MCP token 持久化到本地文件。"""
    try:
        _TOKEN_FILE.write_text(token, encoding="utf-8")
        logger.info(f"MCP token 已缓存至: {_TOKEN_FILE}")
    except Exception as e:
        logger.warning(f"缓存 token 失败: {e}")


def _clear_cached_token() -> None:
    """清除本地缓存的 token 文件。"""
    try:
        _TOKEN_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"清除缓存 token 失败: {e}")


async def _fetch_token_from_server() -> str:
    """
    通过用户名/密码登录，获取并返回新的 MCP 访问令牌，同时写入本地缓存。

    步骤：
    1. POST /api/v4/external/login  →  获取 JWT（在响应头 b-json-web-token 中）
    2. GET  /api/v4/external/mcpToken（携带 JWT）  →  获取 MCP 访问令牌
    """
    if not ENDPOINT:
        raise RuntimeError("ZOOMEYE_BE_ENDPOINT 未设置")
    if not USERNAME or not PASSWORD:
        raise RuntimeError("ZOOMEYE_BE_USERNAME 和 ZOOMEYE_BE_PASSWORD 均为必填项")

    # 忽略自签名证书，与 be-server 保持一致
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        # ── Step 1: 登录获取 JWT ──────────────────────────────────────────────
        logger.info(f"正在登录: {ENDPOINT}/api/v4/external/login")
        login_resp = await client.post(
            f"{ENDPOINT}/api/v4/external/login",
            json={"username": USERNAME, "password": PASSWORD},
        )
        login_resp.raise_for_status()

        # JWT 优先从响应头获取，后备从响应体 data.token 获取
        jwt_token = login_resp.headers.get("b-json-web-token")
        if not jwt_token:
            body = login_resp.json()
            data = body.get("data") or {}
            jwt_token = data.get("token") if isinstance(data, dict) else None

        if not jwt_token:
            raise RuntimeError(f"登录成功但未获取到 JWT，响应: {login_resp.text[:200]}")

        logger.info("登录成功，已获取 JWT")

        # ── Step 2: 获取 MCP 访问令牌 ────────────────────────────────────────
        mcp_resp = await client.get(
            f"{ENDPOINT}/api/v4/external/mcpToken",
            headers={"b-json-web-token": jwt_token},
        )
        mcp_resp.raise_for_status()
        resp_data = mcp_resp.json()

        # 兼容两种返回格式：{ data: { token: "..." } } 或 { data: "..." }
        data_field = resp_data.get("data")
        if isinstance(data_field, dict):
            mcp_token = data_field.get("token")
        elif isinstance(data_field, str) and data_field:
            mcp_token = data_field
        else:
            mcp_token = None

        if not mcp_token:
            raise RuntimeError(f"获取 MCP 令牌失败，响应: {resp_data}")

        logger.info("MCP 访问令牌获取成功")
        _save_token(mcp_token)
        return mcp_token


async def authenticate() -> str:
    """
    获取有效的 MCP 访问令牌。

    优先读取本地缓存（jwt_token 文件），若不存在则走登录流程重新获取并缓存。
    当上游返回 401/403 时，调用方应调用 _clear_cached_token() 后重新 authenticate()。
    """
    cached = _read_cached_token()
    if cached:
        logger.info("使用本地缓存的 MCP token")
        return cached

    logger.info("本地无缓存 token，重新登录获取...")
    return await _fetch_token_from_server()


# ── MCP 服务器定义 ──────────────────────────────────────────────────────────────
app = Server("zoomeye-pro-proxy", version="1.0.0")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """返回从上游 MCP 服务器获取到的工具列表"""
    return _upstream_tools


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.ContentBlock]:
    """将工具调用转发至上游 MCP 服务器"""
    if _upstream_session is None:
        return [types.TextContent(type="text", text="❌ 未连接到上游 MCP 服务器，请检查服务地址和账号配置")]

    try:
        result = await _upstream_session.call_tool(name, arguments)
        return result.content
    except Exception as e:
        logger.error(f"工具调用失败 [{name}]: {e}")
        return [types.TextContent(type="text", text=f"❌ 工具调用失败: {e}")]


# ── 主入口 ──────────────────────────────────────────────────────────────────────
async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    session_manager = StreamableHTTPSessionManager(
        app=app,
        json_response=True,
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(starlette_app: Starlette) -> AsyncIterator[None]:
        global _upstream_session, _upstream_tools

        # ── 认证阶段（最多重试一次：缓存 token 失效时清除后重新登录）──────────────
        mcp_token: str | None = None
        for attempt in range(2):
            try:
                mcp_token = await authenticate()
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"认证失败，清除缓存 token 后重试: {e}")
                    _clear_cached_token()
                else:
                    logger.error(f"认证失败，代理将以离线模式启动: {e}")
                    async with session_manager.run():
                        logger.warning("ZoomEye Pro MCP 代理以离线模式运行（认证失败）")
                        try:
                            yield
                        finally:
                            logger.info("ZoomEye Pro MCP 代理正在关闭...")
                    return

        # ── 连接上游 SSE MCP 服务器（token 失效时自动重新认证重连）────────────
        sse_url = f"{ENDPOINT}/mcp/sse"

        for attempt in range(2):
            logger.info(f"正在连接上游 MCP 服务器 (attempt {attempt + 1}): {sse_url}")
            try:
                async with sse_client(
                    url=sse_url,
                    headers={"x-mcp-token": mcp_token},
                    httpx_client_factory=_no_verify_http_client,
                    sse_read_timeout=300,
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()

                        tools_result = await session.list_tools()
                        _upstream_tools = tools_result.tools
                        _upstream_session = session

                        logger.info(
                            f"上游 MCP 连接成功，共 {len(_upstream_tools)} 个工具可用: "
                            f"{[t.name for t in _upstream_tools]}"
                        )

                        async with session_manager.run():
                            logger.info("ZoomEye Pro MCP 代理服务器已启动")
                            try:
                                yield
                            finally:
                                logger.info("ZoomEye Pro MCP 代理服务器正在关闭...")
                        return  # 正常退出，不需要重试
            except Exception as e:
                logger.error(f"上游 MCP 连接异常: {e}")
                if attempt == 0:
                    # 无论什么错误（500/401/403/网络等），首次失败一律清除缓存重新登录；
                    # 这样切换 endpoint 后也能自动获取新 token。
                    logger.warning("清除缓存 token 并重新登录后重试连接...")
                    _clear_cached_token()
                    try:
                        mcp_token = await _fetch_token_from_server()
                    except Exception as auth_err:
                        logger.error(f"重新登录失败，进入离线模式: {auth_err}")
                        break
                else:
                    break

        # 连接失败时仍然启动，但工具列表为空
        async with session_manager.run():
            logger.warning("ZoomEye Pro MCP 代理以离线模式运行（上游连接失败）")
            try:
                yield
            finally:
                pass
        _upstream_session = None
        _upstream_tools = []

    starlette_app = Starlette(
        debug=True,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    starlette_app = CORSMiddleware(
        starlette_app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE"],
        expose_headers=["Mcp-Session-Id"],
    )

    import uvicorn

    config = uvicorn.Config(starlette_app, host="127.0.0.1", port=0)
    server = uvicorn.Server(config)

    original_startup = server.startup

    async def patched_startup(sockets: list[socket.socket] | None = None):
        await original_startup(sockets)
        for s in server.servers:
            for sock in s.sockets:
                print(json.dumps({"type": "http_start", "port": sock.getsockname()[1]}), flush=True)
                return

    server.startup = patched_startup
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
