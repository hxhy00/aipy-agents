#!/usr/bin/env node

import fs from "node:fs"
import path from "node:path"
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js"
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js"
import pkg from "../manifest.json" with { type: "json" }

const app = createMcpExpressApp()
const systemPrompt = fs.readFileSync(path.join(import.meta.dirname, "prompts/system.txt"), "utf-8")

app.post("/mcp", async (req, res) => {
	const server = getServer()
	try {
		const transport = new StreamableHTTPServerTransport({
			sessionIdGenerator: undefined,
		})
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
				error: {
					code: -32603,
					message: "Internal server error"
				},
				id: null
			})
		}
	}
})

//         监听端口 0，随机选择端口
app.listen(0, function (err) {
	if (err) {
		console.error("Failed to start server:", err)
		process.exit(1)
	}
	// 输出监听的端口号
	console.log(JSON.stringify({
		"type": "http_start",
		"port": this.address().port
	}))
})

/**
 * 初始化MCP Server
 * @returns {McpServer}
 */
function getServer() {
	const server = new McpServer(
		{ name: pkg.name, version: pkg.version },
		{
			//             申明服务有Prompt扩展能力
			capabilities: { prompts: {}, tools: {} },
		}
	)

	// 添加一个空工具避免tools/list报错
	server.registerTool("_", {}, () => {})

	// 系统提示词
	server.registerPrompt(
		"addition-system-instruction",
		{
			description: "document generation prompt",
		},
		() => {
			return {
				"description": "document generation prompt",
				"messages": [
					{
						"role": "user",
						"content": {
							"type": "text",
							"text": systemPrompt
						}
					}
				]
			}
		}
	)

	return server
}

process.on("SIGINT", async () => {
	console.log("Server shutdown complete")
	process.exit(0)
})
