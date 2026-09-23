#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js"
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js"
import pkg from "../manifest.json" with { type: "json" }
import * as readFile from "./tools/read-file.js"


const app = createMcpExpressApp()

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
			capabilities: { tools: {} },
		}
	)

	// 注册工具
	server.registerTool(readFile.toolDefinition.name, readFile.toolDefinition, readFile.handler)

	return server
}

process.on("SIGINT", async () => {
	console.log("Server shutdown complete")
	process.exit(0)
})
