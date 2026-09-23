import fs from "node:fs"
import path from "node:path"
import { z } from "zod"
import { describeDocument, parseFileAsync, parseInput, splitSections } from "../lib/document.js"

export const schema = {
	name: "read_document",
	description: "读取并解析文档（支持 .md / .txt / .docx / .pdf，也可以直接传入文档正文），输出结构化文档模型：目录层级、内容块统计、章节切分建议与每章建议时长。这是「文档 → 成片」流水线的第一步。",
	inputSchema: z.object({
		source: z.string().describe("文档文件路径，或直接传入文档正文内容（含换行的长文本会自动识别为正文）"),
		format: z.string().optional().describe("直接传入正文时指定格式，可选 markdown / text / html，默认 markdown"),
		maxSections: z.number().optional().describe("章节切分上限，超出部分会合并，默认 8，短视频建议 3-5，讲解视频建议 5-10")
	})
}

export async function handler({ source, format = "", maxSections = 8 }) {
	const isFilePath = source.length < 512 && !source.includes("\n")
	let doc
	if (isFilePath) {
		const abs = path.isAbsolute(source) ? source : path.resolve(process.cwd(), source)
		if (!fs.existsSync(abs)) {
			return {
				content: [{ type: "text", text: `文件不存在：${abs}\n\n请确认路径正确，或直接把文档正文内容作为 source 传入。` }],
				isError: true
			}
		}
		doc = await parseFileAsync(abs)
	} else {
		doc = parseInput({ source, format })
	}

	const sections = splitSections(doc, { maxSections })
	const text = describeDocument(doc, sections)

	return {
		content: [{ type: "text", text }],
		structuredContent: {
			title: doc.title,
			source: doc.source,
			format: doc.format,
			stats: doc.stats,
			outline: doc.outline,
			meta: doc.meta || {},
			sections: sections.map(s => ({ title: s.title, level: s.level, charCount: s.charCount, text: s.text })),
			// 完整块结构留给后续步骤，避免对话上下文过大
			blockCount: doc.blocks.length
		}
	}
}
