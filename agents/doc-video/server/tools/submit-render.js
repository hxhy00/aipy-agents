import { z } from "zod"
import { getSpec } from "../lib/specs.js"
import { inspectScript } from "../lib/inspector.js"
import { detectFfmpeg } from "../lib/renderer.js"
import { submitTask, ensureServer } from "../lib/render-server.js"
import { detectAllEngines, DEFAULT_VOICE, VOICES } from "../lib/tts.js"

const shotSchema = z.object({
	index: z.number().describe("分镜序号"),
	kind: z.string().optional().describe("分镜类型"),
	title: z.string().optional().describe("分镜标题"),
	narration: z.string().optional().describe("口播文案（用于配音）"),
	screenText: z.string().optional().describe("屏显文案"),
	sourceText: z.string().optional().describe("原文档摘取素材"),
	durationSec: z.number().optional().describe("分镜时长（秒）"),
	codeBlock: z.string().optional().describe("代码块内容")
})

export const schema = {
	name: "submit_render",
	description: "提交异步渲染任务：把分镜脚本交给独立渲染服务端排期执行，本工具立即返回任务编号（毫秒级），不会阻塞对话。提交后请用 get_render_status 轮询进度，完成后用 get_render_status 的参数取成片路径。注意：一个 3 分钟横屏视频通常需要数分钟渲染，务必不要在对话里同步等待。",
	inputSchema: z.object({
		spec: z.string().describe("视频规格：landscape（横屏知识讲解）或 portrait（竖屏短视频）"),
		shots: z.array(shotSchema).describe("已完成文案策划的分镜脚本（含 narration 与 screenText）"),
		docTitle: z.string().optional().describe("文档标题，用于封面与文件名"),
		voice: z.string().optional().describe(`配音音色，默认 ${DEFAULT_VOICE}。常用：${VOICES.slice(0, 4).map(v => `${v.id}（${v.name}）`).join("、")}`),
		skipQualityCheck: z.boolean().optional().describe("是否跳过渲染前的质检拦截。默认 false，即存在严重问题时拒绝提交，避免浪费渲染时间")
	})
}

export async function handler({ spec, shots = [], docTitle = "", voice = "", skipQualityCheck = false }) {
	const resolved = getSpec(spec)
	if (!shots.length) {
		return { content: [{ type: "text", text: "缺少 shots（分镜脚本）。请先调用 `plan_video` 生成骨架并补齐文案。" }], isError: true }
	}

	// 前置检查 1：渲染能力
	const ffmpeg = await detectFfmpeg()
	if (!ffmpeg.available) {
		return {
			content: [{ type: "text", text: `无法提交渲染：${ffmpeg.reason}\n\n渲染依赖 ffmpeg 做视频编码与拼接。本插件不内置 ffmpeg，请先安装：macOS 执行 brew install ffmpeg，Windows 执行 winget install Gyan.FFmpeg；已安装但仍报未找到时，可在插件设置中用环境变量 FFMPEG_PATH 指定其绝对路径。` }],
			isError: true
		}
	}

	// 前置检查 2：质检拦截
	const qc = inspectScript({ shots, spec: resolved, docTitle })
	if (!qc.passed && !skipQualityCheck) {
		const high = qc.issues.filter(i => i.level === "high")
		return {
			content: [{
				type: "text",
				text: [
					"# 已拦截渲染提交",
					"",
					`分镜脚本存在 ${high.length} 项严重问题，为避免浪费数分钟渲染时间，请先修复：`,
					"",
					...high.map((i, n) => `${n + 1}. ${i.message}${i.fix ? `\n   - 修复建议：${i.fix}` : ""}`),
					"",
					"修复后重新调用 `inspect_script` 复检；若确认可以接受（例如刻意使用某表述），可用 `skipQualityCheck: true` 强制提交。"
				].join("\n")
			}],
			structuredContent: { rejected: true, quality: qc }
		}
	}

	// 提交异步任务
	const info = await ensureServer()
	const ttsEngines = await detectAllEngines()
	const ttsEngine = ttsEngines[0] || null
	const engineLabel = ttsEngines.length
		? ttsEngines.map(e => e.name).join(" → ") + `（音色 ${voice || DEFAULT_VOICE}）`
		: null
	const plan = {
		spec: resolved,
		shots,
		docTitle,
		ttsRate: resolved.ttsRate,
		voice: voice || DEFAULT_VOICE,
		audioClips: []
	}

	const submitted = await submitTask({ plan, spec: resolved, docTitle })
	const totalSec = shots.reduce((n, s) => n + (s.durationSec || 0), 0)
	const estimate = Math.max(20, Math.round(totalSec * 0.6 + shots.length * 3))

	const lines = [
		"# 渲染任务已提交",
		"",
		`- 任务编号：\`${submitted.taskId}\``,
		`- 规格：${resolved.name}（${resolved.width}x${resolved.height}）`,
		`- 分镜数：${shots.length} 个 ｜ 预计成片时长：${Math.round(totalSec)} 秒`,
		`- 配音：${engineLabel || "**未检测到可用配音引擎，将使用静音音轨 + 时长估算**"}`,
		`- 渲染服务端：${submitted.serverUrl}`,
		`- 输出目录：${submitted.outputDir}`,
		`- 预计耗时：约 ${Math.floor(estimate / 60)} 分 ${estimate % 60} 秒`,
		`- 质检结论：${qc.passed ? "通过" : `未通过（质量分 ${qc.score}，已按 skipQualityCheck 强制提交）`}`,
		"",
		"## 重要：不要同步等待",
		"",
		"渲染在独立服务端后台执行，**请立即用 `get_render_status` 查询进度**，不要在当前轮次干等。",
		"建议节奏：先查一次确认任务在跑，之后每隔一段时间查询一次；每次查询都会返回进度百分比与剩余预估。"
	]

	if (!ttsEngines.length) {
		lines.push("", "**配音提示**：未检测到可用配音引擎，成片将是静音画面。两种解决方式：① 配置 Azure 语音（在插件设置中填写 Azure 语音 Key 与区域，音质最佳）；② 本地安装免费引擎 `pip install edge-tts`（或 `uvx edge-tts`）。任选其一，重新提交任务即可获得带配音的成片。")
	} else if (!ttsEngines.some(e => e.name === "azure")) {
		lines.push("", "**配音提示**：当前使用免费 Edge TTS。若需更佳音质与稳定性，可在插件设置中配置 Azure 语音 Key 与区域，系统会自动优先使用 Azure 并在失败时回落到 Edge TTS。")
	}

	return {
		content: [{ type: "text", text: lines.join("\n") }],
		structuredContent: {
			taskId: submitted.taskId,
			status: submitted.status,
			spec: resolved.id,
			specName: resolved.name,
			resolution: `${resolved.width}x${resolved.height}`,
			shotCount: shots.length,
			estimatedDurationSec: Math.round(totalSec),
			estimatedRenderSec: estimate,
			serverUrl: submitted.serverUrl,
			outputDir: submitted.outputDir,
			ttsEngine: ttsEngine?.name || "none",
			ttsEngineChain: ttsEngines.map(e => e.name),
			quality: { passed: qc.passed, score: qc.score, counts: qc.counts }
		}
	}
}
