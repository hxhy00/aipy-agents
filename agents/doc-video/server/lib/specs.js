/**
 * 双规格方案定义：横屏知识讲解 / 竖屏短视频。
 *
 * 规格差异体现在六个维度：
 *   画布尺寸、节奏（语速/单镜时长/总时长）、信息密度、视觉主题、字幕与安全区、成片目标
 * 同一份文档可以被同一套流水线渲染成两种规格，差异全部由这里的规格参数驱动。
 */

export const SPECS = {
	landscape: {
		id: "landscape",
		name: "横屏知识讲解",
		alias: ["横屏", "知识讲解", "landscape", "16:9", "课程", "讲解视频"],
		description: "1920x1080 横屏，完整覆盖文档章节，适合课程、内部培训、技术分享、产品讲解",
		width: 1920,
		height: 1080,
		aspect: "16:9",
		fps: 30,
		safeArea: { top: 80, bottom: 140, left: 120, right: 120 },
		maxDurationSec: 900,
		targetDurationSec: 300,
		minShotSec: 6,
		maxShotSec: 40,
		charsPerSecond: 5.2,
		maxCharsPerShot: 220,
		bulletCount: 4,
		allowSubtitle: true,
		theme: {
			background: "#0F172A",
			foreground: "#E2E8F0",
			accent: "#38BDF8",
			accentSoft: "#1E3A5F",
			muted: "#94A3B8",
			cardBackground: "#16233B",
			fontSize: { title: 96, heading: 64, body: 40, caption: 28 },
			fontFamily: "\"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", sans-serif",
			logoPosition: "top-left",
			transition: "fade"
		},
		emphasis: "信息完整性优先，允许一屏多要点，配图表与代码块",
		structure: ["封面", "目录", "章节正文", "小结"],
		ttsRate: "+8%",
		voiceHint: "讲解语气，语速中等，适合长时间收听"
	},

	portrait: {
		id: "portrait",
		name: "竖屏短视频",
		alias: ["竖屏", "短视频", "portrait", "9:16", "抖音", "视频号", "种草"],
		description: "1080x1920 竖屏，节奏快、单屏单要点，适合短视频平台、朋友圈、社群传播",
		width: 1080,
		height: 1920,
		aspect: "9:16",
		fps: 30,
		safeArea: { top: 260, bottom: 420, left: 80, right: 80 },
		maxDurationSec: 180,
		targetDurationSec: 60,
		minShotSec: 3,
		maxShotSec: 12,
		charsPerSecond: 6.5,
		maxCharsPerShot: 70,
		bulletCount: 1,
		allowSubtitle: true,
		theme: {
			background: "#111827",
			foreground: "#F9FAFB",
			accent: "#FB7185",
			accentSoft: "#7F1D3A",
			muted: "#9CA3AF",
			cardBackground: "#1F2937",
			fontSize: { title: 88, heading: 76, body: 52, caption: 36 },
			fontFamily: "\"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", sans-serif",
			logoPosition: "top-center",
			transition: "slide-up"
		},
		emphasis: "单屏单要点，大字号，前 3 秒必须抛出钩子",
		structure: ["钩子", "痛点/结论", "要点1", "要点2", "要点3", "行动号召"],
		ttsRate: "+18%",
		voiceHint: "节奏偏快、语气有起伏，尾句可上扬"
	}
}

export const SPEC_IDS = Object.keys(SPECS)

/** 宽松解析规格：支持「横屏」「16:9」「知识讲解」「竖屏短视频」等口语化输入 */
export function resolveSpec(input) {
	if (!input) return null
	const key = String(input).toLowerCase().trim().replace(/\s+/g, "")
	for (const spec of Object.values(SPECS)) {
		if (spec.id === key || spec.name === key) return spec
		if (spec.alias.some(a => key.includes(a.toLowerCase()) || a.toLowerCase().includes(key))) return spec
	}
	return null
}

export function getSpec(id) {
	const spec = resolveSpec(id)
	if (!spec) {
		throw new Error(`未知规格「${id}」，可选值：${SPEC_IDS.join(" / ")}（或使用「横屏知识讲解」「竖屏短视频」等中文名）`)
	}
	return spec
}

/**
 * 规格对比表，供规划阶段向用户展示与确认
 */
export function compareSpecs() {
	const rows = [
		["规格", SPECS.landscape.name, SPECS.portrait.name],
		["画布", `${SPECS.landscape.width}x${SPECS.landscape.height}（${SPECS.landscape.aspect}）`, `${SPECS.portrait.width}x${SPECS.portrait.height}（${SPECS.portrait.aspect}）`],
		["目标时长", `约 ${SPECS.landscape.targetDurationSec / 60} 分钟（上限 ${SPECS.landscape.maxDurationSec / 60} 分钟）`, `约 ${SPECS.portrait.targetDurationSec} 秒（上限 ${SPECS.portrait.maxDurationSec} 秒）`],
		["单镜时长", `${SPECS.landscape.minShotSec}-${SPECS.landscape.maxShotSec} 秒`, `${SPECS.portrait.minShotSec}-${SPECS.portrait.maxShotSec} 秒`],
		["单镜字数", `最多 ${SPECS.landscape.maxCharsPerShot} 字`, `最多 ${SPECS.portrait.maxCharsPerShot} 字`],
		["语速", `${SPECS.landscape.charsPerSecond} 字/秒（TTS ${SPECS.landscape.ttsRate}）`, `${SPECS.portrait.charsPerSecond} 字/秒（TTS ${SPECS.portrait.ttsRate}）`],
		["一屏要点", `${SPECS.landscape.bulletCount} 条`, `${SPECS.portrait.bulletCount} 条`],
		["结构", SPECS.landscape.structure.join(" → "), SPECS.portrait.structure.join(" → ")],
		["视觉", `深蓝底 + 青色强调，${SPECS.landscape.theme.transition} 转场`, `暗底 + 玫红强调，${SPECS.portrait.theme.transition} 转场`],
		["适用场景", "课程 / 培训 / 技术分享 / 产品讲解", "短视频平台 / 社群传播 / 朋友圈"],
		["信息策略", SPECS.landscape.emphasis, SPECS.portrait.emphasis]
	]

	const lines = ["# 双规格方案对比", "", `| 维度 | ${SPECS.landscape.name} | ${SPECS.portrait.name} |`, "|:---|:---|:---|"]
	for (const [k, a, b] of rows) lines.push(`| ${k} | ${a} | ${b} |`)
	lines.push("")
	lines.push("同一个文档可以分别产出两种规格，两者共用文案策划层与质检层，只在渲染层按规格参数分流。")
	return lines.join("\n")
}

/**
 * 按规格把章节文本切成「分镜（shot）」草稿。
 * 这是文案策划层的骨架生成，语义润色由模型在此基础上完成。
 */
export function draftShots({ sections, spec, docTitle = "" } = {}) {
	const shots = []
	const push = (kind, title, text, extra = {}) => {
		const cleanText = String(text || "").trim()
		if (!cleanText && !extra.allowEmpty) return
		const chars = cleanText.length
		const seconds = clamp(Math.round(chars / spec.charsPerSecond), spec.minShotSec, spec.maxShotSec)
		shots.push({
			index: shots.length + 1,
			kind,
			title,
			narration: "",
			screenText: "",
			sourceText: cleanText,
			durationSec: seconds,
			...extra
		})
	}

	if (spec.id === "portrait") {
		// 竖屏：钩子 → 要点（严格单点） → 行动号召
		const allSentences = sections
			.flatMap(s => s.text.split(/(?<=[。！？；\n])/))
			.map(s => s.trim())
			.filter(s => s.length > 8)

		const hookSource = allSentences[0] || sections[0]?.title || docTitle
		push("hook", "钩子", splitByChars(hookSource, spec.maxCharsPerShot)[0] || docTitle)

		const keyPoints = []
		for (const section of sections) {
			const sentences = section.text.split(/(?<=[。！？；\n])/).map(s => s.trim()).filter(s => s.length > 10)
			if (!sentences.length) continue
			keyPoints.push({ title: section.title, text: sentences.slice(0, 2).join("") })
			if (keyPoints.length >= 5) break
		}
		keyPoints.forEach((kp, i) => {
			splitByChars(kp.text, spec.maxCharsPerShot).slice(0, 1).forEach(chunk => {
				push("point", `${i + 1}. ${kp.title}`, chunk)
			})
		})
		push("cta", "行动号召", "完整内容见原文档，欢迎收藏转发。")
		return shots
	}

	// 横屏：封面 → 目录 → 章节正文 → 小结
	push("cover", "封面", docTitle || sections[0]?.title || "文档讲解", { allowEmpty: true })
	if (sections.length > 1) {
		push("toc", "目录", sections.map((s, i) => `${i + 1}. ${s.title}`).join("\n"))
	}
	for (const section of sections) {
		// 兼容两种入参：带 blocks 的完整章节（来自文档解析层），以及只有 text 的章节（对话里传递过来的）
		const paragraphs = section.blocks
			? section.blocks
				.filter(b => b.type === "paragraph" || b.type === "list")
				.map(b => (b.type === "list" ? b.items.join("；") : b.text))
				.filter(t => t && t.length > 0)
			: splitByChars(section.text || "", Math.max(40, spec.maxCharsPerShot))

		// 每个章节的正文按单屏容量切成若干分镜，避免一屏塞满
		const chunks = []
		for (const para of paragraphs) {
			splitByChars(para, spec.maxCharsPerShot).forEach(c => chunks.push(c))
		}

		chunks.forEach((chunk, j) => {
			push("section", section.title, chunk, { partIndex: j + 1 })
		})

		const codeBlock = section.blocks?.find(b => b.type === "code")
		if (codeBlock) {
			push("code", `${section.title}（代码）`, `代码示例：${codeBlock.lang || "代码"}`, {
				codeBlock: codeBlock.code.slice(0, 800),
				durationSec: clamp(12, spec.minShotSec, spec.maxShotSec)
			})
		}
	}
	push("summary", "小结", "以上就是本次分享的全部内容。", { allowEmpty: true })

	return shots
}

function splitByChars(text, max) {
	const clean = String(text || "").replace(/\s+/g, " ").trim()
	if (!clean) return []
	if (clean.length <= max) return [clean]
	const parts = []
	const sentences = clean.split(/(?<=[。！？；.!?;])/).map(s => s.trim()).filter(Boolean)
	let buf = ""
	for (const s of sentences) {
		if ((buf + s).length > max && buf) {
			parts.push(buf.trim())
			buf = s
		} else {
			buf += s
		}
	}
	if (buf.trim()) parts.push(buf.trim())
	return parts.length ? parts : [clean.slice(0, max)]
}

function clamp(value, min, max) {
	return Math.max(min, Math.min(max, value))
}

/** 依据分镜清单校验时长是否符合规格约束 */
export function validateDuration(shots, spec) {
	const total = shots.reduce((n, s) => n + (s.durationSec || 0), 0)
	const issues = []
	if (total > spec.maxDurationSec) {
		issues.push(`总时长 ${total} 秒超出规格上限 ${spec.maxDurationSec} 秒，需要精简分镜或压缩文案。`)
	}
	const long = shots.filter(s => (s.durationSec || 0) > spec.maxShotSec)
	if (long.length) {
		issues.push(`有 ${long.length} 个分镜超过单镜上限 ${spec.maxShotSec} 秒（第 ${long.map(s => s.index).join("、")} 个），需要拆分。`)
	}
	const overChars = shots.filter(s => (s.sourceText || "").length > spec.maxCharsPerShot * 1.6)
	if (overChars.length) {
		issues.push(`有 ${overChars.length} 个分镜文案明显超出单屏容量（第 ${overChars.map(s => s.index).join("、")} 个）。`)
	}
	return { totalDurationSec: total, withinLimit: total <= spec.maxDurationSec, issues }
}
