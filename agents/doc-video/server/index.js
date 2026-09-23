#!/usr/bin/env node
/**
 * 讲解视频智能体服务入口
 *
 * 三层拆分：
 *   文案策划层  read_document / plan_video
 *   质检层      inspect_script（提交前）/ 产物校验（渲染完成后自动执行）
 *   渲染层      submit_render / get_render_status —— 实际渲染在独立服务端异步执行
 */

import fs from "node:fs"
import path from "node:path"
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js"
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js"
import pkg from "../manifest.json" with { type: "json" }
import * as readDocument from "./tools/read-document.js"
import * as planVideo from "./tools/plan-video.js"
import * as inspectScript from "./tools/inspect-script.js"
import * as submitRender from "./tools/submit-render.js"
import * as renderStatus from "./tools/render-status.js"

const TOOLS = [readDocument, planVideo, inspectScript, submitRender, renderStatus]

const app = createMcpExpressApp()

function wrap(name, fn) {
	return async (args) => {
		try {
			return await fn(args || {})
		} catch (error) {
			const message = `[${name}] 执行失败：${error?.message || error}`
			console.error(message, error?.stack || "")
			return {
				content: [{ type: "text", text: `${message}\n\n排查建议：确认文档路径可读；调用 get_render_status（不传 taskId）可查看 ffmpeg 解析情况与运行平台。插件已内置 ffmpeg，若仍提示缺失，多为安装不完整或平台不匹配，重新安装插件即可。` }],
				isError: true
			}
		}
	}
}

app.post("/mcp", async (req, res) => {
	const server = getServer()
	try {
		const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined })
		await server.connect(transport)
		await transport.handleRequest(req, res, req.body)
		res.on("close", () => {
			transport.close()
			server.close()
		})
	} catch (error) {
		console.error("Error handling MCP request:", error)
		if (!res.headersSent) {
			res.status(500).json({
				jsonrpc: "2.0",
				error: { code: -32603, message: "Internal server error" },
				id: null
			})
		}
	}
})

app.listen(0, function (err) {
	if (err) {
		console.error("Failed to start server:", err)
		process.exit(1)
	}
	console.log(JSON.stringify({ type: "http_start", port: this.address().port }))
})

function getServer() {
	const server = new McpServer(
		{ name: pkg.name, version: pkg.version },
		{ capabilities: { tools: {}, prompts: {} } }
	)

	for (const tool of TOOLS) {
		server.registerTool(tool.schema.name, tool.schema, wrap(tool.schema.name, tool.handler))
	}

	server.registerPrompt(
		"addition-system-instruction",
		{ description: "文档成片双规格方案、三层职责与异步渲染约定" },
		() => {
			const candidates = [
				path.join(import.meta.dirname, "prompts/addition-system-instruction.txt"),
				path.join(import.meta.dirname, "../prompts/addition-system-instruction.txt")
			]
			let text = ""
			for (const f of candidates) {
				try {
					if (fs.existsSync(f)) { text = fs.readFileSync(f, "utf-8"); break }
				} catch { /* 尝试下一个路径 */ }
			}
			return {
				description: "文档成片双规格方案、三层职责与异步渲染约定",
				messages: [{ role: "user", content: { type: "text", text } }]
			}
		}
	)

	return server
}

process.on("SIGINT", async () => {
	const { closeServer } = await import("./lib/render-server.js")
	await closeServer()
	console.log("Server shutdown complete")
	process.exit(0)
})
