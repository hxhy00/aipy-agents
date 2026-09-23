import asyncio
import socket
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
app = Server("time_server", version="1.0.0")


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.ContentBlock]:
    if name == "current_time":
        import pytz
        from datetime import datetime

        timezone_str = arguments.get("timezone", "UTC")
        try:
            timezone = pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            return [
                types.TextContent(
                    type="text",
                    text=f"Unknown timezone: {timezone_str}",
                )
            ]

        current_time = datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S %Z%z")
        return [
            types.TextContent(
                type="text",
                text=f"Current time in {timezone_str}: {current_time}",
            )
        ]
    
    return [
        types.TextContent(
            type="text",
            text=f"Tool '{name}' not recognized.",
        )
    ]


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="current_time",
            description=("Get the current time from the server"),
            inputSchema={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone to get the current time for (e.g., 'UTC', 'America/New_York')",
                    },
                },
            },
        )
    ]


@app.list_prompts()
async def list_prompts() -> list[types.Prompt]:
    return [
        types.Prompt(
            name="addition-system-instruction",
            title="addition-system-instruction",
            arguments=[],
        )
    ]

@app.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> types.GetPromptResult:
    if name == "addition-system-instruction":
        return {
            "description": "A simple assistant prompt.",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": (
                            "## 附加提示词\n"
                            "这是一个示例附加提示词，用于演示如何扩展对话系统的功能。\n\n"
                        )
                    }
                }
            ]
        }
    
    raise ValueError(f"Unknown prompt: {name}")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create the session manager with our app and event store
    session_manager = StreamableHTTPSessionManager(
        app=app,
        json_response=True,
    )

    # ASGI handler for streamable HTTP connections
    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        """Context manager for managing session manager lifecycle."""
        async with session_manager.run():
            logger.info("Application started with StreamableHTTP session manager!")
            try:
                yield
            finally:
                logger.info("Application shutting down...")

    # Create an ASGI application using the transport
    starlette_app = Starlette(
        debug=True,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    # Wrap ASGI application with CORS middleware to expose Mcp-Session-Id header
    # for browser-based clients (ensures 500 errors get proper CORS headers)
    starlette_app = CORSMiddleware(
        starlette_app,
        allow_origins=["*"],  # Allow all origins - adjust as needed for production
        allow_methods=["GET", "POST", "DELETE"],  # MCP streamable HTTP methods
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
                # 输出监听端口号
                print(json.dumps({ "type": "http_start", "port": sock.getsockname()[1] }), flush=True)
                return

    server.startup = patched_startup
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())

    
        