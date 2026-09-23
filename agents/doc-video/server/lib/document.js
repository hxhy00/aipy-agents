/**
 * 文档解析层：把输入的 .md / .txt / .docx / .pdf 统一解析成结构化文档模型。
 *
 * 输出结构：
 *   { title, source, format, blocks[{type, level, text, items, lang, code}], outline[], stats }
 */

import fs from "node:fs"
import path from "node:path"

/** 从文本解析：支持直接传入内容而非文件 */
export function parseInput({ source = "", format = "" } = {}) {
	if (!source) throw new Error("source 不能为空")

	// 传入的是文件路径
	if (source.length < 512 && !source.includes("\n")) {
		const abs = path.isAbsolute(source) ? source : path.resolve(process.cwd(), source)
		if (fs.existsSync(abs) && fs.statSync(abs).isFile()) {
			return parseFile(abs)
		}
	}
	// 传入的是文档内容
	return parseContent(source, format || "markdown", "(内联内容)")
}

export function parseFile(filePath) {
	const ext = path.extname(filePath).toLowerCase()
	const abs = path.isAbsolute(filePath) ? filePath : path.resolve(process.cwd(), filePath)
	if (!fs.existsSync(abs)) throw new Error(`文件不存在：${abs}`)
	return { ...parseContent(fs.readFileSync(abs, "utf-8"), extToFormat(ext), abs), source: abs }
}

function extToFormat(ext) {
	return { ".md": "markdown", ".markdown": "markdown", ".txt": "text", ".html": "html" }[ext] || "markdown"
}

/**
 * 解析异步文件（docx / pdf 需要异步库）
 */
export async function parseFileAsync(filePath) {
	const ext = path.extname(filePath).toLowerCase()
	const abs = path.isAbsolute(filePath) ? filePath : path.resolve(process.cwd(), filePath)
	if (!fs.existsSync(abs)) throw new Error(`文件不存在：${abs}`)

	if (ext === ".docx") {
		const mammoth = (await import("mammoth")).default
		const result = await mammoth.convertToMarkdown({ path: abs })
		const doc = parseContent(result.value, "markdown", abs)
		doc.notes = (result.messages || []).map(m => m.message).slice(0, 10)
		return doc
	}

	if (ext === ".pdf") {
		const mod = await import("pdf-parse")
		const pdfParse = mod.default || mod
		const data = await pdfParse(fs.readFileSync(abs))
		const text = normalizePdfText(data.text || "")
		const doc = parseContent(text, "text", abs)
		doc.meta.pages = data.numpages
		return doc
	}

	return parseFile(abs)
}

/** PDF 文本修复：合并被断行拆碎的句子，去掉页眉页脚噪声行 */
function normalizePdfText(text) {
	const lines = String(text).split(/\r?\n/)
	const out = []
	for (const raw of lines) {
		const line = raw.trim()
		if (!line) { out.push(""); continue }
		// 纯页码行丢弃
		if (/^\d{1,4}$/.test(line)) continue
		// 中文句子未结束则与下一行拼接，避免把一句话拆成两屏字幕
		if (out.length && !/[。！？；：.!?;:）)】"']$/.test(out[out.length - 1]) && !/^[#\-*\d（(【]/.test(line)) {
			out[out.length - 1] += line
			continue
		}
		out.push(line)
	}
	return out.join("\n")
}

/** 解析文本内容为结构化文档 */
export function parseContent(content, format = "markdown", source = "(内联内容)") {
	const text = String(content || "").replace(/\r\n?/g, "\n")
	if (!text.trim()) throw new Error("文档内容为空")

	const blocks = format === "html" ? parseHtmlBlocks(text) : parseOutlineBlocks(text)
	const title = detectTitle(blocks, source)
	const outline = blocks
		.filter(b => b.type === "heading")
		.map(b => ({ level: b.level, text: b.text }))

	return {
		title,
		source,
		format,
		blocks,
		outline,
		stats: {
			blockCount: blocks.length,
			charCount: text.length,
			headingCount: outline.length,
			paragraphCount: blocks.filter(b => b.type === "paragraph").length,
			listCount: blocks.filter(b => b.type === "list").length,
			codeCount: blocks.filter(b => b.type === "code").length,
			tableCount: blocks.filter(b => b.type === "table").length,
			readingMinutes: Math.max(1, Math.round(text.replace(/\s/g, "").length / 400))
		}
	}
}

/** 逐行解析 Markdown / 纯文本 */
function parseOutlineBlocks(text) {
	const lines = text.split("\n")
	const blocks = []
	let i = 0
	let inCode = false
	let codeBuf = []
	let codeLang = ""

	while (i < lines.length) {
		const line = lines[i]
		const trimmed = line.trim()

		// 代码块
		if (/^```/.test(trimmed)) {
			if (inCode) {
				blocks.push({ type: "code", lang: codeLang, code: codeBuf.join("\n").trim() })
				codeBuf = []
				inCode = false
			} else {
				inCode = true
				codeLang = trimmed.slice(3).trim()
			}
			i++
			continue
		}
		if (inCode) {
			codeBuf.push(line)
			i++
			continue
		}

		if (!trimmed) { i++; continue }

		// 标题
		const heading = trimmed.match(/^(#{1,6})\s+(.*)$/)
		if (heading) {
			blocks.push({ type: "heading", level: heading[1].length, text: cleanInline(heading[2]) })
			i++
			continue
		}

		// 表格
		if (/^\|.*\|$/.test(trimmed)) {
			const rows = []
			while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) {
				rows.push(lines[i].trim().split("|").slice(1, -1).map(c => cleanInline(c.trim())))
				i++
			}
			const header = rows[0] || []
			const body = rows.slice(1).filter(r => !r.every(c => /^:?-{2,}:?$/.test(c)))
			blocks.push({ type: "table", header, rows: body })
			continue
		}

		// 列表
		if (/^([-*+]|\d+[.、)])\s+/.test(trimmed)) {
			const items = []
			while (i < lines.length) {
				const cur = lines[i].trim()
				const m = cur.match(/^([-*+]|\d+[.、)])\s+(.*)$/)
				if (!m) break
				items.push(cleanInline(m[2]))
				i++
			}
			blocks.push({ type: "list", ordered: /^\d/.test(trimmed), items })
			continue
		}

		// 引用
		if (/^>\s?/.test(trimmed)) {
			const buf = []
			while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
				buf.push(lines[i].trim().replace(/^>\s?/, ""))
				i++
			}
			blocks.push({ type: "quote", text: cleanInline(buf.join(" ")) })
			continue
		}

		// 段落（连续非空行合并）
		const buf = [trimmed]
		i++
		while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\||>\s?|```|[-*+]\s|\d+[.、)]\s)/.test(lines[i].trim())) {
			buf.push(lines[i].trim())
			i++
		}
		blocks.push({ type: "paragraph", text: cleanInline(buf.join(" ")) })
	}

	return blocks
}

function parseHtmlBlocks(html) {
	// 轻量 HTML → 块级结构转换，覆盖 h1-h6 / p / ul / ol / pre / blockquote
	const blocks = []
	const re = /<(h[1-6]|p|li|pre|blockquote)[^>]*>([\s\S]*?)<\/\1>/gi
	let m
	while ((m = re.exec(html))) {
		const tag = m[1].toLowerCase()
		const inner = cleanInline(stripTags(m[2]))
		if (!inner) continue
		if (tag.startsWith("h")) {
			blocks.push({ type: "heading", level: Number(tag[1]), text: inner })
		} else if (tag === "li") {
			const last = blocks[blocks.length - 1]
			if (last?.type === "list") last.items.push(inner)
			else blocks.push({ type: "list", ordered: false, items: [inner] })
		} else if (tag === "pre") {
			blocks.push({ type: "code", lang: "", code: stripTags(m[2]).trim() })
		} else if (tag === "blockquote") {
			blocks.push({ type: "quote", text: inner })
		} else {
			blocks.push({ type: "paragraph", text: inner })
		}
	}
	return blocks.length ? blocks : [{ type: "paragraph", text: cleanInline(stripTags(html)) }]
}

function stripTags(html) {
	return String(html).replace(/<[^>]+>/g, " ")
}

/** 清理行内 Markdown 标记，保留纯文本 */
export function cleanInline(text) {
	return String(text ?? "")
		.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")          // 图片
		.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")            // 链接
		.replace(/`([^`]+)`/g, "$1")                        // 行内代码
		.replace(/(\*\*|__)(.*?)\1/g, "$2")                 // 加粗
		.replace(/(\*|_)(.*?)\1/g, "$2")                    // 斜体
		.replace(/~~(.*?)~~/g, "$1")                        // 删除线
		.replace(/<[^>]+>/g, "")                            // 残留标签
		.replace(/\s+/g, " ")
		.trim()
}

function detectTitle(blocks, source) {
	const first = blocks.find(b => b.type === "heading" && b.level === 1)
	if (first) return first.text
	const anyH = blocks.find(b => b.type === "heading")
	if (anyH) return anyH.text
	const firstPara = blocks.find(b => b.type === "paragraph")
	if (firstPara) return firstPara.text.slice(0, 40)
	return path.basename(String(source || "未命名文档"))
}

/**
 * 章节切分：按一级/二级标题把文档拆成适合成片的章节
 */
export function splitSections(doc, { maxSections = 8, minChars = 80 } = {}) {
	const sections = []
	let current = { title: doc.title, level: 1, blocks: [] }

	for (const block of doc.blocks) {
		const isSectionBreak = block.type === "heading" && (block.level <= 2 || sections.length === 0 && block.level <= 3)
		if (isSectionBreak && current.blocks.length) {
			if (flattenText(current).length >= minChars) sections.push(finalize(current))
			current = { title: block.text, level: block.level, blocks: [] }
			continue
		}
		if (isSectionBreak && !current.blocks.length) {
			current.title = block.text
			current.level = block.level
			continue
		}
		current.blocks.push(block)
	}
	if (current.blocks.length) {
		if (flattenText(current).length >= minChars || sections.length === 0) sections.push(finalize(current))
	}

	// 章节过多时按字数合并尾部，保证成片节奏
	if (sections.length > maxSections) {
		const head = sections.slice(0, maxSections - 1)
		const tail = sections.slice(maxSections - 1)
		head.push({
			title: "其他要点",
			level: 2,
			text: tail.map(s => s.text).join("\n\n"),
			charCount: tail.reduce((n, s) => n + s.charCount, 0),
			blocks: tail.flatMap(s => s.blocks)
		})
		return head
	}
	return sections
}

function finalize(section) {
	const text = flattenText(section)
	return {
		title: section.title,
		level: section.level,
		text,
		charCount: text.length,
		blocks: section.blocks
	}
}

function flattenText(section) {
	return section.blocks.map(b => {
		if (b.type === "code") return `（代码片段：${b.lang || "代码"}）`
		if (b.type === "list") return b.items.join("；")
		if (b.type === "table") return `表格：${b.header.join("、")}`
		return b.text || ""
	}).filter(Boolean).join("\n")
}

/** 生成文档概览，供规划阶段使用 */
export function describeDocument(doc, sections) {
	const lines = [
		`# 文档解析结果`,
		"",
		`- 标题：${doc.title}`,
		`- 来源：${doc.source}`,
		`- 格式：${doc.format}`,
		"",
		"## 结构统计",
		"",
		`- 内容块：${doc.stats.blockCount} 个（段落 ${doc.stats.paragraphCount}、列表 ${doc.stats.listCount}、代码 ${doc.stats.codeCount}、表格 ${doc.stats.tableCount}）`,
		`- 标题层级：${doc.stats.headingCount} 个`,
		`- 正文字数：约 ${doc.stats.charCount} 字`,
		`- 预计阅读时长：约 ${doc.stats.readingMinutes} 分钟`,
		""
	]

	if (doc.outline.length) {
		lines.push("## 文档目录", "")
		for (const h of doc.outline) {
			lines.push(`${"  ".repeat(Math.max(0, h.level - 1))}- ${h.text}`)
		}
		lines.push("")
	}

	lines.push("## 章节切分建议", "")
	lines.push(`共切分为 ${sections.length} 个可成片章节：`, "")
	lines.push("| 序号 | 章节标题 | 字数 | 建议时长 |")
	lines.push("|:---|:---|:---|:---|")
	sections.forEach((s, i) => {
		const seconds = Math.max(8, Math.round(s.charCount / 5.2))
		lines.push(`| ${i + 1} | ${s.title} | ${s.charCount} | 约 ${seconds} 秒 |`)
	})
	lines.push("")
	lines.push("**下一步**：调用 `plan_video` 选择规格（横屏知识讲解 / 竖屏短视频）并生成分镜脚本。")

	return lines.join("\n")
}
