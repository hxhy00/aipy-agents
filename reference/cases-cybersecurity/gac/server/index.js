import fs from "node:fs"
import path from "node:path"
import { Server } from "@modelcontextprotocol/sdk/server/index.js"
import {
	CallToolRequestSchema,
	ListToolsRequestSchema,
	ErrorCode,
	McpError,
	ListPromptsRequestSchema,
	GetPromptRequestSchema,
} from "@modelcontextprotocol/sdk/types.js"
import { streamableHttp } from "common/streamableHttp.js"
import pkg from "../manifest.json" with { type: "json" }
import * as ip from "./tools/ip.js"
import * as domain from "./tools/domain.js"

const TOOLS = {
	"ip": ip,
	"domain": domain,
}

const PROMPTS = {
	"addition-system-instruction": {
		schema: {
			"name": "addition-system-instruction",
			"description": "log analysis prompt",
			"arguments": [],
		},
		handler() {
			const filePath = path.join(
				import.meta.dirname,
				process.env.NODE_ENV === "production"
					? "prompts/addition-system-instruction.txt"
					: "../prompts/addition-system-instruction.txt"
			)
			if (fs.existsSync(filePath)) {
				return fs.readFileSync(filePath, "utf-8")
			}
			return ""
		}
	}
}

const mcpServer = new Server(
	{ name: pkg.name, version: pkg.version },
	{ capabilities: { tools: {}, prompts: {} } }
)

const TOOLS_SCHEMA = Object.values(TOOLS).map(tool => tool.schema)
mcpServer.setRequestHandler(ListToolsRequestSchema, async (request) => {
	return {
		tools: TOOLS_SCHEMA,
	}
})

const PROMPTS_SCHEMA = Object.values(PROMPTS).map(prompt => prompt.schema)
mcpServer.setRequestHandler(ListPromptsRequestSchema, async (request) => {
	return {
		prompts: PROMPTS_SCHEMA,
	}
})

mcpServer.setRequestHandler(CallToolRequestSchema, async (request) => {
	const tool = TOOLS[request.params.name]
	if (tool) {
		return tool.handler(request.params.arguments, request.params.name)
	} else {
		console.error(`调用未支持的工具: ${request.params.name}`)
		throw new McpError(
			ErrorCode.MethodNotFound,
			`未知工具: ${request.params.name}`
		)
	}
})

mcpServer.setRequestHandler(GetPromptRequestSchema, async (request) => {
	const prompt = PROMPTS[request.params.name]
	if (!prompt) {
		return {
			isError: true,
			messages: [{
				content: {
					type: "text",
					text: `Prompt not found: ${request.params.name}`,
				}
			}]
		}
	}
	return {
		"description": prompt.schema.description,
		"messages": [
			{
				"role": "user",
				"content": {
					"type": "text",
					"text": prompt.handler(request.params.arguments || {})
				}
			}
		]
	}
})

streamableHttp(mcpServer)
