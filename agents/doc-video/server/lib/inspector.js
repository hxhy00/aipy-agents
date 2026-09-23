/**
 * 质检层：成片前的规则化检查 + 成片后的产物校验。
 *
 * 质检分两道关：
 *   第一关（提交渲染前）检查分镜脚本——时长、单屏字数、敏感词、钩子强度、结构完整性
 *   第二关（渲染完成后）检查产物文件——是否存在、大小是否合理、音视频轨是否齐全、时长是否吻合
 */

import fs from "node:fs"

const RISK_WORDS = [
	"最好", "第一", "唯一", "国家级", "世界级", "绝对", "100%有效", "永久有效",
	"包治", "稳赚", "保证收益", "零风险", "必然", "史上最"
]

const AI_TRACE_WORDS = [
	"作为AI", "作为一个AI", "我是AI", "language model", "大语言模型",
	"根据我的训练数据", "以下是我为您", "希望以上内容对您有帮助", "如有其他问题"
]

const FILLER_WORDS = ["嗯", "呃", "那个", "这个的话", "就是说", "总而言之就是说"]

/**
 * 提交渲染前的分镜脚本质检
 * @param {object} params
 * @param {object[]} params.shots 分镜脚本
 * @param {object} params.spec 规格
 */
export function inspectScript({ shots = [], spec, docTitle = "" } = {}) {
	if (!spec) throw new Error("质检缺少 spec（规格参数）")
	if (!shots.length) throw new Error("质检缺少 shots（分镜脚本）")

	const items = []
	const add = (level, code, message, shotIndex = null, fix = "") => {
		items.push({ level, code, message, shotIndex, fix })
	}

	const normalized = shots.filter(s => String(s.narration || s.screenText || s.sourceText || "").trim().length > 0)

	// 1. 结构完整性
	const kinds = new Set(normalized.map(s => s.kind))
	const required = spec.id === "portrait" ? ["hook", "cta"] : ["cover"]
	for (const kind of required) {
		if (!kinds.has(kind)) {
			add("high", "missing-structure", `缺少必备结构「${kindLabel(kind)}」，${spec.id === "portrait" ? "短视频必须有钩子与行动号召" : "讲解视频应有封面"}`, null,
				kind === "hook" ? "把最有冲击力的结论前置到第 1 个分镜作为钩子" : "补一个对应类型的分镜")
		}
	}

	// 2. 时长约束
	const totalDuration = normalized.reduce((n, s) => n + (s.durationSec || 0), 0)
	if (spec.id === "portrait" && totalDuration > spec.maxDurationSec) {
		add("high", "duration-exceed", `总时长 ${Math.round(totalDuration)} 秒，超过短视频上限 ${spec.maxDurationSec} 秒`, null, "删减次要要点，或把结论合并进钩子")
	}
	if (totalDuration < 10) {
		add("medium", "duration-too-short", `总时长仅 ${Math.round(totalDuration)} 秒，内容过于单薄`, null, "补充要点分镜或展开讲解")
	}
	if (spec.id === "portrait" && totalDuration > spec.targetDurationSec * 1.5) {
		add("medium", "duration-over-target", `总时长 ${Math.round(totalDuration)} 秒，明显超出目标 ${spec.targetDurationSec} 秒`, null, "控制要点在 3-5 个")
	}

	// 3. 单镜约束
	normalized.forEach(shot => {
		const text = String(shot.narration || shot.screenText || shot.sourceText || "").trim()
		const dur = shot.durationSec || 0
		if (dur > spec.maxShotSec) {
			add("medium", "shot-too-long", `第 ${shot.index} 个分镜时长 ${dur} 秒，超过单镜上限 ${spec.maxShotSec} 秒`, shot.index, "拆成两个分镜")
		}
		if (spec.allowSubtitle && text.length > spec.maxCharsPerShot * 1.6) {
			add("medium", "shot-text-overflow", `第 ${shot.index} 个分镜 ${text.length} 字，超出单屏容量（约 ${spec.maxCharsPerShot} 字），画面会溢出`, shot.index, "精简文案或拆分分镜")
		}
		if (/[A-Za-z]{8,}/.test(text) && spec.id === "portrait") {
			add("low", "long-latin", `第 ${shot.index} 个分镜含较长英文串，竖屏窄版式下易折行错位`, shot.index, "改用中文表述或拆分")
		}
		if (/(。)？$|，$|、$/.test(text)) {
			add("low", "trailing-punctuation", `第 ${shot.index} 个分镜文案以不完整标点结尾`, shot.index, "补全句子")
		}
	})

	// 4. 首镜钩子强度（竖屏专项）
	if (spec.id === "portrait") {
		const hook = normalized.find(s => s.kind === "hook") || normalized[0]
		const hookText = String(hook?.narration || hook?.screenText || hook?.sourceText || "")
		if (hookText.length > 40) {
			add("high", "weak-hook-length", `钩子文案 ${hookText.length} 字，前 3 秒讲不完，完播率会掉`, hook?.index, "压缩到 25 字以内，直接抛结论或反差")
		}
		if (!/\d|为什么|居然|其实|别再|一定|千万|揭秘|误区|真相|对比/.test(hookText)) {
			add("medium", "weak-hook-appeal", "钩子缺少数字或悬念词，吸引力不足", hook?.index, "加入具体数字、反常识结论或明确收益")
		}
	}

	// 5. 表达质量
	const allText = normalized.map(s => String(s.narration || s.screenText || s.sourceText || "")).join("\n")
	for (const word of RISK_WORDS) {
		if (allText.includes(word)) {
			add("high", "risk-word", `出现极限/承诺性表述「${word}」，平台可能限流或涉及违规`, null, "改为有依据的客观表述，如「目前较优」「在 X 场景下表现更好」")
		}
	}
	for (const word of AI_TRACE_WORDS) {
		if (allText.includes(word)) {
			add("medium", "ai-trace", `出现 AI 痕迹表述「${word}」，会削弱可信度`, null, "删除该句，直接从正文结论开始")
		}
	}
	const fillerHits = FILLER_WORDS.filter(w => allText.includes(w))
	if (fillerHits.length) {
		add("low", "filler", `口语填充词偏多：${fillerHits.join("、")}`, null, "精简口播文案，删掉无信息量的连接词")
	}
	if (spec.id === "portrait" && normalized.length > 12) {
		add("low", "too-many-shots", `分镜数 ${normalized.length} 个，短视频节奏会显零碎`, null, "合并到 6-10 个分镜")
	}

	// 6. 语速一致性（估算时长与分镜时长是否吻合）
	normalized.forEach(shot => {
		const text = String(shot.narration || shot.screenText || shot.sourceText || "")
		const estimated = text.replace(/\s/g, "").length / spec.charsPerSecond
		if (Math.abs(estimated - (shot.durationSec || 0)) > Math.max(4, estimated * 0.6)) {
			add("low", "duration-mismatch", `第 ${shot.index} 个分镜标注 ${shot.durationSec} 秒，按语速估算约 ${Math.round(estimated)} 秒，音画可能不同步`, shot.index, "按估算值修正 durationSec")
		}
	})

	const counts = { high: 0, medium: 0, low: 0 }
	items.forEach(i => counts[i.level]++)

	return {
		stage: "script",
		spec: spec.id,
		shotCount: normalized.length,
		totalDurationSec: Math.round(totalDuration),
		withinDurationLimit: totalDuration <= spec.maxDurationSec,
		passed: counts.high === 0,
		counts,
		score: Math.max(0, 100 - counts.high * 18 - counts.medium * 8 - counts.low * 3),
		issues: items
	}
}

function kindLabel(kind) {
	return { cover: "封面", toc: "目录", hook: "钩子", point: "要点", section: "章节正文", code: "代码示例", summary: "小结", cta: "行动号召" }[kind] || kind
}

/**
 * 渲染完成后的产物质检
 * @param {object} params
 * @param {string} params.videoPath 成片路径
 * @param {object} params.spec 规格
 * @param {number} [params.expectedDurationSec]
 * @param {object} [params.probeInfo] ffprobe 探测结果（可选）
 */
export async function inspectOutput({ videoPath, spec, expectedDurationSec = 0, probeInfo = null } = {}) {
	const items = []
	const add = (level, code, message, fix = "") => items.push({ level, code, message, shotIndex: null, fix })

	if (!videoPath || !fs.existsSync(videoPath)) {
		add("high", "file-missing", `成片文件不存在：${videoPath}`, "检查渲染任务日志，确认 ffmpeg 是否执行成功")
		return { stage: "output", passed: false, counts: { high: 1, medium: 0, low: 0 }, score: 0, issues: items, file: null }
	}

	const stat = fs.statSync(videoPath)
	if (stat.size < 20 * 1024) {
		add("high", "file-too-small", `成片仅 ${(stat.size / 1024).toFixed(1)} KB，几乎肯定是渲染失败的空文件`, "检查分镜画面生成与 ffmpeg 日志")
	} else if (stat.size < 200 * 1024) {
		add("medium", "file-small", `成片 ${(stat.size / 1024).toFixed(0)} KB 偏小，可能画面单调或音轨缺失`, "确认配音是否成功合成")
	}

	if (probeInfo) {
		const { width, height, durationSec, hasAudio, hasVideo } = probeInfo
		if (hasVideo === false) add("high", "no-video-stream", "成片缺少视频轨", "检查分段渲染命令")
		if (hasAudio === false) add("medium", "no-audio-stream", "成片缺少音频轨（可能是配音合成失败后走了静音兜底）", "检查 edge-tts 是否可用，或改用已生成的静音版本")
		if (width && height && (width !== spec.width || height !== spec.height)) {
			add("high", "resolution-mismatch", `成片分辨率 ${width}x${height} 与规格 ${spec.width}x${spec.height} 不一致`, "检查规格参数是否在渲染链路被覆盖")
		}
		if (durationSec && expectedDurationSec && Math.abs(durationSec - expectedDurationSec) > Math.max(5, expectedDurationSec * 0.2)) {
			add("medium", "duration-drift", `成片实际时长 ${durationSec} 秒，与预期 ${expectedDurationSec} 秒偏差较大`, "核对分镜时长与配音时长")
		}
		if (spec.id === "portrait" && durationSec && durationSec > spec.maxDurationSec) {
			add("high", "portrait-too-long", `竖屏成片 ${durationSec} 秒，超出平台常见时长上限`, "删减分镜后重新渲染")
		}
	}

	const counts = { high: 0, medium: 0, low: 0 }
	items.forEach(i => counts[i.level]++)

	return {
		stage: "output",
		passed: counts.high === 0,
		counts,
		score: Math.max(0, 100 - counts.high * 25 - counts.medium * 10 - counts.low * 3),
		file: { path: videoPath, sizeBytes: stat.size, sizeText: `${(stat.size / 1024 / 1024).toFixed(2)} MB` },
		probe: probeInfo,
		issues: items
	}
}

/** 把质检结果渲染成可读报告 */
export function formatInspection(result) {
	const lines = []
	const stageName = result.stage === "script" ? "分镜脚本质检" : "成片产物质检"
	lines.push(`# ${stageName}结果`)
	lines.push("")
	lines.push(`- 结论：**${result.passed ? "通过" : "未通过"}**（质量分 ${result.score}/100）`)
	lines.push(`- 问题分布：严重 ${result.counts.high} 项 ｜ 中等 ${result.counts.medium} 项 ｜ 轻微 ${result.counts.low} 项`)
	if (result.stage === "script") {
		lines.push(`- 分镜数：${result.shotCount} 个 ｜ 预计成片时长：${result.totalDurationSec} 秒 ｜ 时长合规：${result.withinDurationLimit ? "是" : "否"}`)
	}
	if (result.file) {
		lines.push(`- 成片：${result.file.path}（${result.file.sizeText}）`)
	}
	lines.push("")

	if (!result.issues.length) {
		lines.push("未发现明显问题。")
		return lines.join("\n")
	}

	const order = { high: 0, medium: 1, low: 2 }
	const levelName = { high: "严重", medium: "中等", low: "轻微" }
	for (const level of ["high", "medium", "low"]) {
		const list = result.issues.filter(i => i.level === level)
		if (!list.length) continue
		lines.push(`## ${levelName[level]}问题（${list.length} 项）`, "")
		list.forEach((i, idx) => {
			const loc = i.shotIndex ? `（分镜 ${i.shotIndex}）` : ""
			lines.push(`${idx + 1}. ${i.message}${loc}`)
			if (i.fix) lines.push(`   - 修复建议：${i.fix}`)
		})
		lines.push("")
	}

	if (!result.passed) {
		lines.push("---", "", "**存在严重问题，建议先修复再渲染**：把上面的修复建议应用到分镜脚本后，重新调用 `inspect_script` 复检。")
	} else if (result.counts.medium) {
		lines.push("---", "", "**质检通过**，但仍有中等及以下问题，可选择性优化后再渲染。")
	}
	lines.push("")
	void order
	return lines.join("\n")
}
