import { z } from "zod"
import { formatInspection, inspectScript } from "../lib/inspector.js"
import { getSpec } from "../lib/specs.js"

const shotSchema = z.object({
	index: z.number().describe("分镜序号"),
	kind: z.string().optional().describe("分镜类型：cover / toc / hook / point / section / code / summary / cta"),
	title: z.string().optional().describe("分镜标题（屏显主标题）"),
	narration: z.string().optional().describe("口播文案"),
	screenText: z.string().optional().describe("屏显文案"),
	sourceText: z.string().optional().describe("原文档摘取素材"),
	durationSec: z.number().optional().describe("该分镜时长（秒）"),
	codeBlock: z.string().optional().describe("代码块内容（如有）")
})

export const schema = {
	name: "inspect_script",
	description: "分镜脚本质检：在提交渲染前检查分镜脚本的结构完整性、总时长与单镜时长是否超限、单屏字数是否溢出、竖屏钩子是否够强、是否含极限承诺/违规词或 AI 痕迹。存在严重问题时不应直接渲染。",
	inputSchema: z.object({
		spec: z.string().describe("视频规格：landscape（横屏知识讲解）或 portrait（竖屏短视频）"),
		shots: z.array(shotSchema).describe("待质检的分镜脚本（plan_video 返回的 shots，补齐 narration 与 screenText 后传入）"),
		docTitle: z.string().optional().describe("文档标题")
	})
}

export async function handler({ spec, shots = [], docTitle = "" }) {
	const resolved = getSpec(spec)
	const result = inspectScript({ shots, spec: resolved, docTitle })
	const text = formatInspection(result)

	const tips = []
	if (!result.passed) {
		tips.push("", "**处理建议**：先把「严重问题」全部修掉——尤其是时长超限、缺少钩子、极限承诺词这三类，它们会直接影响成片可用性。修完后重新调用本工具复检。")
	}
	tips.push("", "**下一步**：质检通过后，把 `shots` 原样传给 `submit_render` 提交异步渲染任务。")

	return {
		content: [{ type: "text", text: text + tips.join("\n") }],
		structuredContent: result
	}
}
