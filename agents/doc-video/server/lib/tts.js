/**
 * 配音合成层：双引擎 + 自动降级。
 *
 * 引擎优先级：
 *   1. Azure Speech（配置了 AZURE_SPEECH_KEY + AZURE_SPEECH_REGION 时优先，音质与稳定性最佳）
 *   2. edge-tts（免费、免密钥、中文音色自然，作为兜底）
 *   3. 静音占位音轨 + 按字估算时长（全部引擎不可用时的最终兜底，保证渲染链路始终可跑通）
 *
 * Azure 与 Edge 的音色名完全通用（如 zh-CN-XiaoxiaoNeural），语速格式也一致（如 "+8%"），
 * 因此切换到 Azure 后用户无需改动任何既有配置。
 *
 * 时长估算规则与 specs.js 的 charsPerSecond 保持一致，避免音画不同步。
 */

import fs from "node:fs"
import path from "node:path"
import { commandAvailable, resolveBinary, runBinary } from "./binaries.js"

export { commandAvailable }

const DEFAULT_VOICE = process.env.VIDEO_EDGE_TTS_VOICE || "zh-CN-XiaoxiaoNeural"

/** 语音候选：中文优先，按性别/风格分组，供用户选择 */
export const VOICES = [
	{ id: "zh-CN-XiaoxiaoNeural", name: "晓晓（女声·通用）", style: "温和自然，适合知识讲解" },
	{ id: "zh-CN-XiaoyiNeural", name: "晓伊（女声·活力）", style: "轻快活泼，适合短视频" },
	{ id: "zh-CN-YunxiNeural", name: "云希（男声·阳光）", style: "清晰有精神，适合产品讲解" },
	{ id: "zh-CN-YunjianNeural", name: "云健（男声·解说）", style: "低沉稳重，适合解说" },
	{ id: "zh-CN-YunyangNeural", name: "云扬（男声·播报）", style: "标准播音腔，适合新闻播报" },
	{ id: "zh-CN-XiaochenNeural", name: "晓辰（女声·知性）", style: "知性平静，适合课程" },
	{ id: "zh-CN-liaoning-XiaobeiNeural", name: "晓北（女声·东北）", style: "方言特色" },
	{ id: "zh-HK-HiuMaanNeural", name: "曉曼（粤语女声）", style: "粤语内容" }
]

/** Azure Speech 配置：Key 与 Region 必须同时存在才认为可用 */
function azureConfig() {
	const key = String(process.env.AZURE_SPEECH_KEY || "").trim()
	const region = String(process.env.AZURE_SPEECH_REGION || "").trim()
	if (!key || !region) return null
	return { key, region }
}

export function azureAvailable() {
	return Boolean(azureConfig())
}

/**
 * 探测 TTS 引擎，按优先级返回首个可用引擎。
 * Azure 只做配置检查（不做网络探测，避免每次合成前多一次往返），实际失败时在合成阶段降级。
 */
export async function detectAllEngines() {
	const engines = []
	const azure = azureConfig()
	if (azure) {
		engines.push({ name: "azure", key: azure.key, region: azure.region })
	}
	const edge = await detectTtsEngine()
	if (edge) engines.push(edge)
	return engines
}

/** 探测可用的 TTS 后端（解析为绝对路径，避免 GUI 进程 PATH 缺失导致误判不可用） */
export async function detectTtsEngine() {
	const candidates = [
		{ name: "edge-tts", cmd: "edge-tts", args: ["--help"] },
		{ name: "python-edge-tts", cmd: "python3", args: ["-m", "edge_tts", "--help"] },
		{ name: "uvx-edge-tts", cmd: "uvx", args: ["edge-tts", "--help"] }
	]
	for (const c of candidates) {
		const resolved = resolveBinary(c.cmd)
		if (!resolved) continue
		try {
			const res = await runBinary(resolved, c.args, { timeoutMs: 8000 })
			if (res.code === 0) return { ...c, cmd: resolved }
		} catch { /* 尝试下一个候选 */ }
	}
	return null
}

/**
 * 合成分镜配音
 * @param {object} params
 * @param {object[]} params.shots 分镜（需含 narration 或 screenText）
 * @param {string} [params.voice]
 * @param {string} [params.rate] 语速，如 "+10%"
 * @param {string} params.outDir 输出目录
 * @returns {Promise<{engine:string, voice:string, clips:object[], totalDurationSec:number, errors:string[]}>}
 */
export async function synthesize({ shots = [], voice = DEFAULT_VOICE, rate = "+8%", outDir } = {}) {
	await fs.promises.mkdir(outDir, { recursive: true })
	const engines = await detectAllEngines()
	const clips = []
	const errors = []
	/** 实际产出声音的引擎集合，用于回传真实使用的引擎 */
	const usedEngines = new Set()

	for (const shot of shots) {
		const text = String(shot.narration || shot.screenText || shot.sourceText || "").trim()
		const fileName = `audio-${String(shot.index).padStart(3, "0")}.mp3`
		const filePath = path.join(outDir, fileName)

		if (!text) {
			clips.push({ index: shot.index, file: null, durationSec: shot.durationSec || 3, engine: "none", silent: true })
			continue
		}

		const estimated = estimateDuration(text, rate)
		let ok = false
		let usedEngine = ""

		// 按优先级依次尝试每个引擎，任一成功即停止；全部失败则静音占位
		for (const engine of engines) {
			try {
				await runTts(engine, { text, voice, rate, outPath: filePath })
				if (fs.existsSync(filePath) && fs.statSync(filePath).size > 1024) {
					ok = true
					usedEngine = engine.name
					usedEngines.add(engine.name)
					break
				}
			} catch (error) {
				errors.push(`第 ${shot.index} 个分镜使用 ${engine.name} 配音失败：${error.message}`)
			}
		}

		if (ok) {
			const measured = await probeDuration(filePath)
			clips.push({
				index: shot.index,
				file: filePath,
				durationSec: measured || estimated,
				estimated: !measured,
				engine: usedEngine
			})
		} else {
			clips.push({
				index: shot.index,
				file: null,
				durationSec: estimated,
				engine: "estimated",
				silent: true,
				text
			})
		}
	}

	const used = Array.from(usedEngines)
	return {
		engine: used.length === 0 ? "none" : used.length === 1 ? used[0] : `mixed(${used.join("+")})`,
		voice,
		rate,
		availableEngines: engines.map(e => e.name),
		clips,
		totalDurationSec: Math.round(clips.reduce((n, c) => n + c.durationSec, 0) * 10) / 10,
		errors
	}
}

async function runTts(engine, { text, voice, rate, outPath }) {
	if (engine.name === "azure") return runAzureTts(engine, { text, voice, rate, outPath })
	let args
	if (engine.name === "edge-tts") {
		args = ["--voice", voice, "--rate", rate, "--text", text, "--write-media", outPath]
	} else if (engine.name === "python-edge-tts") {
		args = ["-m", "edge_tts", "--voice", voice, "--rate", rate, "--text", text, "--write-media", outPath]
	} else {
		args = ["edge-tts", "--voice", voice, "--rate", rate, "--text", text, "--write-media", outPath]
	}
	// engine.cmd 在探测阶段已解析为绝对路径；此处再兜底解析一次，避免缓存失效后回退到裸命令
	const cmd = path.isAbsolute(engine.cmd) ? engine.cmd : resolveBinary(engine.cmd)
	if (!cmd) throw new Error(`未找到配音引擎「${engine.cmd}」，请安装 edge-tts`)
	try {
		const res = await runBinary(cmd, args, { timeoutMs: 60000 })
		if (res.code !== 0) throw new Error(res.stderr.trim().slice(0, 300) || `edge-tts 退出码 ${res.code}`)
	} catch (error) {
		if (/超时/.test(error.message)) throw new Error("配音合成超时（60 秒）")
		throw error
	}
}

/** XML 转义：SSML 文本中 & < > " ' 必须转义，否则请求会被 Azure 拒绝 */
function escapeXml(value) {
	return String(value)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&apos;")
}

/**
 * Azure Speech 合成：REST 接口直连，无需额外 SDK 依赖。
 * 端点：https://{region}.tts.speech.microsoft.com/cognitiveservices/v1
 * 输出格式与默认 mp3 产物保持一致（24kHz / 48kbit / 单声道）。
 */
async function runAzureTts(engine, { text, voice, rate, outPath }) {
	const ssml = [
		`<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">`,
		`<voice name="${escapeXml(voice)}">`,
		`<prosody rate="${escapeXml(rate)}">${escapeXml(text)}</prosody>`,
		`</voice>`,
		`</speak>`
	].join("")

	const endpoint = `https://${engine.region}.tts.speech.microsoft.com/cognitiveservices/v1`
	const controller = new AbortController()
	const timer = setTimeout(() => controller.abort(), 60000)

	try {
		const res = await fetch(endpoint, {
			method: "POST",
			signal: controller.signal,
			headers: {
				"Ocp-Apim-Subscription-Key": engine.key,
				"Content-Type": "application/ssml+xml",
				"X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
				"User-Agent": "aipy-doc-video"
			},
			body: ssml
		})

		if (!res.ok) {
			const detail = await res.text().catch(() => "")
			// 401/403 为密钥问题，404 多为区域写错，便于用户定位
			throw new Error(`Azure 合成失败 HTTP ${res.status}: ${String(detail).slice(0, 200)}`)
		}

		const buffer = Buffer.from(await res.arrayBuffer())
		if (!buffer.length) throw new Error("Azure 返回空音频")
		await fs.promises.writeFile(outPath, buffer)
	} finally {
		clearTimeout(timer)
	}
}

/** 用 ffprobe 读取真实音频时长（绝对路径调用，不依赖 PATH） */
async function probeDuration(file) {
	const resolved = resolveBinary("ffprobe")
	if (!resolved) return null
	try {
		const res = await runBinary(resolved, ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file], { timeoutMs: 15000 })
		const num = Number(String(res.stdout).trim())
		return Number.isFinite(num) && num > 0 ? Math.round(num * 10) / 10 : null
	} catch {
		return null
	}
}

let ffprobeCache = null
export async function probeAvailable() {
	if (ffprobeCache !== null) return ffprobeCache
	ffprobeCache = await commandAvailable("ffprobe", ["-version"])
	return ffprobeCache
}

/** 按语速估算朗读时长，与 specs 的 charsPerSecond 对齐 */
export function estimateDuration(text, rate = "+0%") {
	const chars = String(text || "").replace(/\s/g, "").length
	const rateFactor = 1 + (parseInt(String(rate).replace(/[^-\d]/g, ""), 10) || 0) / 100
	const base = chars / 5.2
	const seconds = base / (rateFactor || 1)
	return Math.max(2, Math.round(seconds * 10) / 10)
}

export { DEFAULT_VOICE }
