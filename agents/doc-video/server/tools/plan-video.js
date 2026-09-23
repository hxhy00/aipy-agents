import { z } from "zod"
import { SPECS, compareSpecs, draftShots, getSpec, validateDuration } from "../lib/specs.js"

const sectionSchema = z.object({
	title: z.string().describe("章节标题"),
	level: z.number().optional().describe("标题层级"),
	charCount: z.number().optional().describe("章节字数"),
	text: z.string().describe("章节正文")
})

export const schema = {
	name: "plan_video",
	description: "视频规格规划：选择横屏知识讲解（1920x1080）或竖屏短视频（1080x1920）规格，按规格把文档章节切成分镜骨架，并给出时长校验与文案策划要求。这是文案策划层的第一步。不传 spec 参数时，返回两种规格的对比表供用户选择。",
	inputSchema: z.object({
		spec: z.string().optional().describe("视频规格，可选 landscape（横屏知识讲解，16:9）、portrait（竖屏短视频，9:16）。也接受「横屏」「竖屏短视频」「知识讲解」等中文说法。不传则只返回规格对比表"),
		docTitle: z.string().optional().describe("文档标题，用于封面分镜"),
		sections: z.array(sectionSchema).optional().describe("read_document 返回的 sections 原样传入"),
		targetDurationSec: z.number().optional().describe("期望成片时长（秒）。不传则使用规格默认目标时长：横屏 300 秒，竖屏 60 秒"),
		voice: z.string().optional().describe("配音音色标识，如 zh-CN-XiaoxiaoNeural。不传则用默认音色")
	})
}

export async function handler({ spec = "", docTitle = "", sections = [], targetDurationSec = 0, voice = "" }) {
	// 未指定规格：返回对比表，让用户先选
	if (!spec) {
		return {
			content: [{
				type: "text",
				text: [
					compareSpecs(),
					"",
					"请确认使用哪种规格后，再次调用 `plan_video` 并传入 spec 参数（landscape 或 portrait）。",
					"如需同时产出两种规格，可以先按横屏走完流水线，再用同一份 sections 走竖屏流水线，两层文案与质检逻辑完全复用。"
				].join("\n")
			}],
			structuredContent: {
				specs: Object.values(SPECS).map(s => ({
					id: s.id, name: s.name, resolution: `${s.width}x${s.height}`, aspect: s.aspect,
					targetDurationSec: s.targetDurationSec, maxDurationSec: s.maxDurationSec,
					maxCharsPerShot: s.maxCharsPerShot, structure: s.structure
				}))
			}
		}
	}

	const resolved = getSpec(spec)
	if (!sections.length) {
		return {
			content: [{ type: "text", text: "缺少 sections 参数。请先调用 `read_document` 解析文档，再把返回的 sections 传进来。" }],
			isError: true
		}
	}

	const shots = draftShots({ sections, spec: resolved, docTitle })
	const validation = validateDuration(shots, resolved)

	const budget = targetDurationSec || resolved.targetDurationSec
	const charsPerShot = resolved.maxCharsPerShot
	const estimatedShots = Math.ceil(budget / ((resolved.minShotSec + resolved.maxShotSec) / 2))

	const lines = [
		`# 视频规格规划：${resolved.name}`,
		"",
		`- 画布：${resolved.width}x${resolved.height}（${resolved.aspect}） ｜ 帧率 ${resolved.fps}fps`,
		`- 目标时长：${budget} 秒 ｜ 上限 ${resolved.maxDurationSec} 秒`,
		`- 单镜约束：${resolved.minShotSec}-${resolved.maxShotSec} 秒 / 单镜最多 ${charsPerShot} 字 / 一屏 ${resolved.bulletCount} 个要点`,
		`- 结构：${resolved.structure.join(" → ")}`,
		`- 信息策略：${resolved.emphasis}`,
		"",
		"## 分镜骨架（共 " + shots.length + " 个）",
		"",
		"| # | 类型 | 标题 | 原文摘取 | 预估时长 |",
		"|:---|:---|:---|:---|:---|",
		...shots.map(s => `| ${s.index} | ${kindLabel(s.kind)} | ${s.title.slice(0, 24)} | ${(s.sourceText || "").replace(/\|/g, "/").slice(0, 40)}… | ${s.durationSec}s |`),
		"",
		"## 时长校验",
		"",
		`- 分镜合计：${validation.totalDurationSec} 秒 ｜ 合规：${validation.withinLimit ? "是" : "**否**"}`,
		...validation.issues.map(i => `- ⚠️ ${i}`),
		""
	]

	if (!validation.issues.length) lines.push("- 时长与单镜容量均在规格范围内。", "")

	lines.push(
		"## 文案策划要求（下一步必须完成）",
		"",
		"骨架里的 `sourceText` 只是从原文摘取的素材，**不能直接当口播稿**。请在提交渲染前为每个分镜补齐两个字段：",
		"",
		"1. `narration`（口播文案）：口语化、可朗读，去掉书面语与括号补充；长度控制在单镜字数上限内",
		"2. `screenText`（屏显文案）：画面上的文字，比口播更短、更凝练，突出关键词",
		"",
		`额外约束：`,
		`- 语速按 ${resolved.charsPerSecond} 字/秒估算，时长要与字数匹配`,
	resolved.id === "portrait"
			? "- 第 1 个分镜（hook）必须在 25 字内抛出钩子：用数字、反常识结论或明确收益留住观众"
			: "- 每个章节的讲解要有过渡句，避免生硬跳转",
		"",
		"**下一步**：把补齐后的分镜脚本调用 `inspect_script` 做质检；质检通过后再调用 `submit_render` 提交渲染。"
	)

	return {
		content: [{ type: "text", text: lines.join("\n") }],
		structuredContent: {
			spec: resolved.id,
			specName: resolved.name,
			resolution: `${resolved.width}x${resolved.height}`,
			aspect: resolved.aspect,
			targetDurationSec: budget,
			maxDurationSec: resolved.maxDurationSec,
			charsPerSecond: resolved.charsPerSecond,
			maxCharsPerShot: charsPerShot,
			minShotSec: resolved.minShotSec,
			maxShotSec: resolved.maxShotSec,
			ttsRate: resolved.ttsRate,
			structure: resolved.structure,
			theme: resolved.theme,
			shots,
			validation,
			voice: voice || process.env.VIDEO_EDGE_TTS_VOICE || "zh-CN-XiaoxiaoNeural"
		}
	}
}

function kindLabel(kind) {
	return { cover: "封面", toc: "目录", hook: "钩子", point: "要点", section: "章节正文", code: "代码示例", summary: "小结", cta: "行动号召" }[kind] || kind
}
