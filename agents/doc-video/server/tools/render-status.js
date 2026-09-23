import fs from "node:fs"
import { z } from "zod"
import { formatInspection, inspectOutput } from "../lib/inspector.js"
import { getSpec } from "../lib/specs.js"
import { getServerInfo, getTask, listTasks } from "../lib/render-server.js"
import { probeAvailable } from "../lib/tts.js"
import { resolveBinary, runBinary, describeBinaries } from "../lib/binaries.js"

export const schema = {
	name: "get_render_status",
	description: "查询渲染任务状态。传 taskId 查单个任务（返回进度百分比、当前阶段、已完成耗时与剩余预估；完成后自动对成片做产物质检并返回文件路径与大小）；不传 taskId 则列出全部任务。这是唯一需要在对话里重复调用的工具，用于追踪异步渲染进度。",
	inputSchema: z.object({
		taskId: z.string().optional().describe("渲染任务编号。不传则列出本会话的全部任务"),
		includeLogs: z.boolean().optional().describe("是否附带任务日志（最近 25 条），排查问题时用，默认 false")
	})
}

export async function handler({ taskId = "", includeLogs = false }) {
	if (!taskId) {
		const info = getServerInfo()
		const tasks = listTasks()
		const bins = describeBinaries()
		const lines = [
			"# 渲染任务列表",
			"",
			`- 渲染服务端：${info.running ? `运行中（${info.url}）` : "未启动（尚未提交过任务）"}`,
			`- 输出目录：${info.workDir || "尚未确定"}`,
			`- 队列：排队 ${info.queued} 个 ｜ 渲染中 ${info.running} 个`,
			`- 运行平台：${bins.platform}`,
			`- ffmpeg：${bins.ffmpeg.path ? `${bins.ffmpeg.path}（来源：${sourceLabel(bins.ffmpeg.source)}）` : "**未找到**"}`,
			`- ffprobe：${bins.ffprobe.path ? `${bins.ffprobe.path}（来源：${sourceLabel(bins.ffprobe.source)}）` : "未找到（时长探测将跳过，不影响成片）"}`,
			""
		]
		if (!bins.ffmpeg.path) {
			lines.push(
				"**警告**：未找到 ffmpeg，无法渲染成片。",
				"",
				"插件通常已内置 ffmpeg；若出现此提示，说明内置二进制缺失或与当前平台不匹配。",
				"解决办法：① 重新安装插件以恢复内置二进制；② 在插件设置中通过环境变量 `FFMPEG_PATH` 指定 ffmpeg 绝对路径。",
				""
			)
		}
		if (tasks.length) {
			lines.push("| 任务编号 | 规格 | 状态 | 进度 | 阶段 | 提交时间 |")
			lines.push("|:---|:---|:---|:---|:---|:---|")
			for (const t of tasks) {
				lines.push(`| \`${t.taskId}\` | ${t.specName} | ${statusLabel(t.status)} | ${t.progress}% | ${t.detail} | ${t.createdAt?.slice(11, 19) || "—"} |`)
			}
		} else {
			lines.push("暂无任务。请先调用 `submit_render` 提交渲染任务。")
		}
		return { content: [{ type: "text", text: lines.join("\n") }], structuredContent: { server: info, tasks } }
	}

	const task = await getTask(taskId)
	if (!task) {
		return {
			content: [{ type: "text", text: `未找到任务 \`${taskId}\`。可调用本工具（不传 taskId）查看全部任务编号。` }],
			isError: true
		}
	}

	const lines = [
		`# 渲染任务 ${task.taskId}`,
		"",
		`- 状态：**${statusLabel(task.status)}**`,
		`- 进度：${task.progress}% ｜ 当前阶段：${stageLabel(task.stage)}`,
		`- 说明：${task.detail}`,
		`- 规格：${task.specName}（${task.resolution}） ｜ 分镜 ${task.shotCount} 个`,
		`- 提交时间：${task.createdAt} ｜ 已耗时：${task.elapsedSec} 秒`,
		""
	]

	if (task.status === "running" || task.status === "queued") {
		const remaining = estimateRemaining(task)
		lines.push(`- 剩余预估：约 ${remaining}`, "")
		lines.push("**下一步**：任务还在渲染中，请稍后再查一次；不要在对话里同步等待。")
		lines.push("")
		lines.push("提示：如果希望减少往返次数，可以在用户确认「不着急」的情况下间隔较长时间再查；视频越长，渲染越慢（长视频会自动降速渲染以避免过载）。")
	}

	if (task.status === "failed") {
		lines.push("## 失败原因", "", task.error || "未知错误", "")
		lines.push("**排查建议**：", "1. 确认 ffmpeg 可用：`ffmpeg -version`", "2. 查看任务日志定位失败阶段（可用 includeLogs: true）", "3. 若为配音失败，可安装 edge-tts 或先按静音版本渲染", "")
	}

	if (task.status === "succeeded" && task.result) {
		lines.push("## 成片产物", "")
		lines.push(`- 文件：${task.result.output}`)
		lines.push(`- 大小：${task.result.sizeText} ｜ 时长：${task.result.durationSec} 秒 ｜ 分辨率：${task.result.resolution} ｜ 帧率：${task.result.fps}`)
		lines.push(`- 音轨：${task.result.hasAudio ? "已合成配音" : "静音（未合成配音）"}`)
		if (task.audio) {
			lines.push(`- 配音引擎：${task.audio.engine || "none"} ｜ 音色：${task.audio.voice || "—"} ｜ 配音总长：${task.audio.totalDurationSec || 0} 秒`)
			if (task.audio.errors?.length) {
				lines.push(`- 配音警告 ${task.audio.errors.length} 条：${task.audio.errors.slice(0, 3).join("；")}`)
			}
		}
		lines.push("")

		// 产物自动质检
		try {
			const spec = getSpec(task.spec)
			const probe = await probeVideo(task.result.output)
			const outputQc = await inspectOutput({
				videoPath: task.result.output,
				spec,
				expectedDurationSec: task.result.durationSec,
				probeInfo: probe
			})
			lines.push(formatInspection(outputQc))
		} catch (error) {
			lines.push(`产物校验失败：${error.message}`, "")
		}

		lines.push("", "**任务已完成**：成片已落盘，可直接使用。如需重新调整，修改分镜脚本后重新提交即可（两种规格可并行渲染）。")
	}

	if (includeLogs && task.logs?.length) {
		lines.push("", "## 任务日志（最近 25 条）", "", "```", ...task.logs, "```")
	}

	return { content: [{ type: "text", text: lines.join("\n") }], structuredContent: task }
}

function statusLabel(status) {
	return { queued: "排队中", running: "渲染中", succeeded: "已完成", failed: "失败", cancelled: "已取消" }[status] || status
}

function sourceLabel(source) {
	return { env: "环境变量指定", builtin: "插件内置", path: "系统 PATH", system: "常见安装路径", missing: "未找到" }[source] || source
}

function stageLabel(stage) {
	return {
		queued: "排队等待", audio: "配音合成", render: "画面渲染",
		concat: "分段拼接", finalize: "生成成片", done: "已完成"
	}[stage] || stage
}

function estimateRemaining(task) {
	const spec = { portrait: 0.5, landscape: 0.8 }[task.spec] || 0.7
	const base = Math.max(15, Math.round((task.estimatedDurationSec || 60) * spec + (task.shotCount || 5) * 3))
	const remain = Math.max(3, Math.round(base * (1 - task.progress / 100)))
	return remain > 60 ? `${Math.floor(remain / 60)} 分 ${remain % 60} 秒` : `${remain} 秒`
}

/** 用 ffprobe 读取成片真实参数（绝对路径调用，不依赖 PATH） */
async function probeVideo(file) {
	if (!(await probeAvailable())) return null
	const resolved = resolveBinary("ffprobe")
	if (!resolved || !fs.existsSync(file)) return null
	try {
		const res = await runBinary(resolved, [
			"-v", "error", "-show_entries",
			"stream=codec_type,width,height:format=duration",
			"-of", "json", file
		], { timeoutMs: 20000 })
		const data = JSON.parse(res.stdout)
		const streams = data.streams || []
		const video = streams.find(s => s.codec_type === "video")
		const audio = streams.find(s => s.codec_type === "audio")
		return {
			hasVideo: Boolean(video),
			hasAudio: Boolean(audio),
			width: video?.width,
			height: video?.height,
			durationSec: Math.round((Number(data.format?.duration) || 0) * 10) / 10
		}
	} catch {
		return null
	}
}
