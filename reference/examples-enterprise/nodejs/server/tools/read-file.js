import fs from "node:fs/promises"
import * as z from "zod/v4"

export const toolDefinition = {
	name: "read_file",
	description: "Read Text File",
	inputSchema: {
		filePath: z.string().describe("Path to the file to be read"),
		encoding: z.string().optional().describe("File encoding, default is 'utf-8'"),
	},
}

/**
 * Handler for the read_file tool
 * @param {{ filePath: string, encoding?: string }} params
 * @returns {Promise<CallToolResult>}
 */
export async function handler({ filePath, encoding = "utf-8" }) {
	return {
		content: [
			{
				type: "text",
				text: await fs.readFile(filePath, encoding)
			}
		]
	}
}
