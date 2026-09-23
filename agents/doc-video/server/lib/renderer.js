/**
 * 渲染执行层：把分镜脚本渲染为成片。
 *
 * 设计取舍（重要）：
 *   分镜画面用 HTML/CSS 描述，交给无头浏览器截图成 PNG，再由 ffmpeg 合成视频。
 *   之所以不用 Remotion / puppeteer：两者都要拉取数 GB 的浏览器内核与依赖；
 *   这里直接复用系统里已有的 Chrome / Edge / Chromium，零额外安装成本。
 *   之所以不用「SVG 文件 + 转换器」：ffmpeg 多数发行版不带 SVG 解码器，
 *   rsvg-convert / resvg 又需要单独 brew 安装，链路不稳。
 *   若目标环境完全没有浏览器，会降级为「纯色底图 + ffmpeg drawtext 烧字」，
 *   中文由系统的 PingFang / Hiragino 字体渲染，保证成片可用而不是空白。
 */

import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { spawn } from "node:child_process"
import { commandAvailable, describeBinaries, resolveBinary, runBinary } from "./binaries.js"

/**
 * 探测 ffmpeg 是否可用（渲染能力的硬前置）。
 * 解析顺序：内置二进制 → PATH → 常见安装路径，详见 lib/binaries.js。
 */
export async function detectFfmpeg() {
	const info = describeBinaries()
	if (!info.ffmpeg.path) {
		return {
			available: false,
			ffprobe: false,
			resolved: info,
			reason: [
				"未检测到 ffmpeg，无法渲染成片。",
				`（当前平台：${info.platform}）请任选一种方式安装：`,
				"① macOS：终端执行 brew install ffmpeg；",
				"② Windows：终端执行 winget install Gyan.FFmpeg（或 scoop install ffmpeg）；",
				"③ 其他方式安装后若仍检测不到，可在插件设置里用环境变量 FFMPEG_PATH 直接指定 ffmpeg 绝对路径。",
				"安装完成后无需重启插件，重新调用一次即可生效。"
			].join("")
		}
	}
	const hasFfprobe = await commandAvailable("ffprobe", ["-version"])
	return { available: true, ffprobe: hasFfprobe, resolved: info }
}

const BROWSER_CANDIDATES = process.platform === "win32"
	? [
		`${process.env["ProgramFiles"] || "C:\\Program Files"}\\Google\\Chrome\\Application\\chrome.exe`,
		`${process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)"}\\Google\\Chrome\\Application\\chrome.exe`,
		`${process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)"}\\Microsoft\\Edge\\Application\\msedge.exe`,
		`${process.env["ProgramFiles"] || "C:\\Program Files"}\\Microsoft\\Edge\\Application\\msedge.exe`,
		`${process.env.LOCALAPPDATA || ""}\\Google\\Chrome\\Application\\chrome.exe`
	]
	: [
		"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
		"/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
		"/Applications/Chromium.app/Contents/MacOS/Chromium",
		"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
		"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
		"/usr/bin/google-chrome",
		"/usr/bin/chromium",
		"/usr/bin/chromium-browser",
		"/usr/bin/microsoft-edge",
		"/snap/bin/chromium"
	]

let browserCache = null

/** 定位可用的无头浏览器（Chrome / Edge / Chromium），结果缓存 */
export async function findBrowser() {
	if (browserCache !== null) return browserCache
	const paths = [...BROWSER_CANDIDATES]
	// 解析器自带 PATH 与常见目录回退，能覆盖 GUI 进程 PATH 不完整的情况
	for (const cmd of ["google-chrome", "chromium", "chromium-browser", "microsoft-edge", "chrome"]) {
		const found = resolveBinary(cmd)
		if (found) paths.push(found)
	}
	browserCache = paths.find(p => p && fs.existsSync(p)) || null
	return browserCache
}

/** 渲染能力总览，供工具向用户说明当前环境的降级情况 */
export async function detectRenderCapability() {
	const ffmpeg = await detectFfmpeg()
	const browser = await findBrowser()
	return {
		ffmpeg: ffmpeg.available,
		ffmpegReason: ffmpeg.reason || "",
		browser: browser ? path.basename(browser) : null,
		mode: !ffmpeg.available ? "unavailable" : browser ? "browser" : "drawtext-fallback",
		note: !ffmpeg.available
			? "缺少 ffmpeg，无法渲染成片"
			: browser
				? `使用 ${path.basename(browser)} 无头截图渲染`
				: "未检测到 Chrome/Edge/Chromium，将降级为 ffmpeg drawtext 烧字（排版较简，建议安装浏览器以获得完整版式）"
	}
}


/** 转义 CSS 字符串中的特殊字符（用于 font-family 等属性值内部） */
function escapeCss(text) {
	return String(text ?? "").replace(/\\/g, "\\\\").replace(/"/g, '\\"')
}

/** 把规格里的字体名规范化为带引号的 CSS 字体栈，避免内嵌双引号破坏属性 */
function cssFontStack(spec) {
	const raw = spec.theme.fontFamily || "sans-serif"
	// 去掉原字符串里可能存在的引号，再统一加一层
	const names = raw.split(",").map(s => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean)
	return names.map(n => `"${escapeCss(n)}"`).join(", ")
}

/** 折行：按像素宽度估算每行字数 */
/**
 * 折行：用离屏 canvas 按实际字体像素宽度测量（与截图渲染同一引擎），
 * 避免「按字数估算」在中英文混排、标点字宽差异下溢出或提前断行。
 * @param {string} text 原文（\n 视为强制换行）
 * @param {number} maxWidthPx 可用宽度（像素）
 * @param {number} maxLines 最大行数
 */
async function wrapLines(text, maxWidthPx, maxLines, fontSpec, browser) {
	const raw = String(text || "").replace(/[ \t]+/g, " ").trim()
	if (!raw) return []
	const paragraphs = raw.split(/\n+/).map(p => p.trim()).filter(Boolean)
	// 没有 fontSpec 就无法做任何真实度量，只能用字数估算
	if (!fontSpec) return wrapByChars(raw, Math.max(8, Math.floor(maxWidthPx / 52)), maxLines)

	const widthOf = line => textWidth(line, fontSpec, browser)
	// 度量能力探测：字体文件能用就不需要 browser，也避免逐字 spawn 浏览器进程
	const probe = await widthOf("测")
	if (!probe && (!browser || !fontSpec)) return wrapByChars(raw, Math.max(8, Math.floor(maxWidthPx / 52)), maxLines)
	const lines = []
	for (const para of paragraphs) {
		let cur = ""
		for (const ch of para) {
			const test = cur + ch
			if (cur && (await widthOf(test)) > maxWidthPx) {
				lines.push(cur)
				cur = ch
				if (lines.length >= maxLines) break
			} else {
				cur = test
			}
		}
		if (cur) lines.push(cur)
		if (lines.length >= maxLines) break
	}
	const truncated = lines.length > maxLines
	const out = lines.slice(0, maxLines)
	if (truncated) {
		const last = [...out[maxLines - 1]]
		while (last.length > 1 && (await widthOf(last.join("") + "…")) > maxWidthPx) last.pop()
		out[maxLines - 1] = last.join("") + "…"
	}
	return tidyBreaks(out, widthOf, maxWidthPx)
}

/** canvas 不可用时的降级：按字数估算折行 */
function wrapByChars(raw, maxCharsPerLine, maxLines) {
	const paragraphs = raw.split(/\n+/).map(p => p.trim()).filter(Boolean)
	const lines = []
	for (const para of paragraphs) {
		let buf = ""
		for (const ch of para) {
			buf += ch
			if ([...buf].length >= maxCharsPerLine) {
				lines.push(buf)
				buf = ""
				if (lines.length >= maxLines) break
			}
		}
		if (buf) lines.push(buf)
		if (lines.length >= maxLines) break
	}
	const truncated = lines.length > maxLines
	const out = lines.slice(0, maxLines)
	if (truncated) out[maxLines - 1] = [...out[maxLines - 1]].slice(0, Math.max(1, maxCharsPerLine - 1)).join("") + "…"
	return out
}

/**
 * 文本宽度测量：用 opentype.js 直接解析字体文件计算字宽（advanceWidth）。
 *
 * 为什么不再起浏览器：旧实现为每一段文本都拉起一个 headless Chrome 进程做
 * SVG getComputedTextLength，一次成片要起几百个进程，是折行阶段的主要耗时。
 * 改为读同款字体文件做纯计算后，单次测量从「进程级」降到「函数级」。
 *
 * 降级链：字体文件度量 → 浏览器度量 → 按字数估算（wrapByChars）。
 */

// 字体族名 → 系统字体文件候选（按优先级）
const FONT_FILE_CANDIDATES = {
	"pingfang sc": [
		"/System/Library/Fonts/PingFang.ttc",
		"/System/Library/AssetsV2/com_apple_MobileAsset_Font7/3419f2a427639ad8c8e139149a287865a90fa17e.asset/AssetData/PingFang.ttc"
	],
	"hiragino sans gb": ["/System/Library/Fonts/Hiragino Sans GB.ttc"],
	"microsoft yahei": ["C:\\Windows\\Fonts\\msyh.ttc"],
	"noto sans cjk sc": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
	"source han sans sc": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
}

/**
 * 通用兜底字体文件：包含完整 CJK 字形，且是标准单体 SFNT，
 * 不像 PingFang.ttc 那样需要拆 TTC（拆出来的表偏移在部分 macOS 版本上仍不可解）。
 * 只要它在，就能覆盖「字体族未登记 / 登记的 ttc 解析失败」的情况。
 */
const FALLBACK_FONT_FILES = [
	"/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
	"C:\\Windows\\Fonts\\msyh.ttf",
	"/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
	"/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
]

// fontSpec -> { font, source } 对象（null 表示已尝试但不可用）
const otFontCache = new Map()
// `${fontSpec}|${line}` -> 宽度
let measureCache = new Map()

/** 度量来源统计，便于诊断「为什么这行字宽不准」 */
export const measureStats = { font: 0, browser: 0, estimate: 0, lastFontFile: null }

let otModule
/** 惰性加载 opentype.js；未安装时返回 null 以便降级 */
async function loadOpentype() {
	if (otModule !== undefined) return otModule
	try {
		const mod = await import("opentype.js")
		otModule = mod.default || mod
	} catch {
		otModule = null
	}
	return otModule
}

/**
 * 从 fontSpec（如 `700 48px "PingFang SC", sans-serif`）解析出字号与字体族
 */
function parseFontSpec(fontSpec) {
	const str = String(fontSpec || "")
	const sizeMatch = str.match(/(\d+(?:\.\d+)?)px/)
	const size = sizeMatch ? Number(sizeMatch[1]) : 16
	const families = [...str.matchAll(/"([^"]+)"|'([^']+)'|([A-Za-z][\w\s-]*)/g)]
		.map(m => (m[1] || m[2] || m[3] || "").trim().toLowerCase())
		.filter(Boolean)
	return { size, families }
}

/**
 * 从 .ttc 字体集合中取出第一个 SFNT，并把表偏移修正为相对子块起点。
 * opentype.js 只支持单体字体文件，ttc 需要先拆。
 */
function extractFirstSfnt(buf, ot) {
	if (buf.length < 12) return null
	const tag = buf.toString("ascii", 0, 4)
	if (tag !== "ttcf") return buf
	const numFonts = buf.readUInt32BE(8)
	if (!numFonts || 12 + numFonts * 4 > buf.length) return null
	const off = buf.readUInt32BE(12) // 取第一个字体
	if (off <= 0 || off >= buf.length) return null
	const sub = Buffer.from(buf.subarray(off))
	const numTables = sub.readUInt16BE(8)
	if (12 + numTables * 16 > sub.length) return sub
	// ttc 内各表的 offset 是相对整个文件的，拆出后需减去子块起点
	for (let i = 0; i < numTables; i++) {
		const rec = 12 + i * 16
		const abs = sub.readUInt32BE(rec + 8)
		if (abs < off) continue
		sub.writeUInt32BE(abs - off, rec + 8)
	}
	return sub
}

/** 尝试解析单个字体文件，失败返回 null */
function parseFontFile(file, ot) {
	try {
		if (!fs.existsSync(file)) return null
		const buf = fs.readFileSync(file)
		const sfnt = extractFirstSfnt(buf, ot)
		if (!sfnt) return null
		return ot.parse(sfnt.buffer.slice(sfnt.byteOffset, sfnt.byteOffset + sfnt.byteLength))
	} catch {
		return null
	}
}

/** 按字体族找到并解析字体文件，结果缓存 */
async function resolveOtFont(fontSpec) {
	const key = String(fontSpec || "")
	if (otFontCache.has(key)) return otFontCache.get(key)

	const ot = await loadOpentype()
	if (!ot) { otFontCache.set(key, null); return null }

	const { families } = parseFontSpec(key)
	let font = null
	let file = null
	// 1) 优先按声明的字体族精确匹配
	for (const family of families) {
		const files = FONT_FILE_CANDIDATES[family]
		if (!files) continue
		for (const candidate of files) {
			font = parseFontFile(candidate, ot)
			if (font) { file = candidate; break }
		}
		if (font) break
	}
	// 2) 精确匹配全部失败 → 用通用 CJK 兜底字体，保证「宽算得准」优先于「字形完全一致」
	if (!font) {
		for (const candidate of FALLBACK_FONT_FILES) {
			font = parseFontFile(candidate, ot)
			if (font) { file = candidate; break }
		}
	}

	const result = font ? { font, file } : null
	if (file) measureStats.lastFontFile = file
	otFontCache.set(key, result)
	return result
}

/**
 * 文本宽度测量（对外统一入口）。
 * @returns {Promise<number|null>} 像素宽度；null 表示需走字数估算降级
 */
export async function textWidth(line, fontSpec, browser) {
	const text = String(line ?? "")
	if (!text) return 0
	const key = `${fontSpec}|${text}`
	if (measureCache.has(key)) return measureCache.get(key)

	const { size } = parseFontSpec(fontSpec)

	// 首选：字体文件度量（纯计算，无进程开销）
	const resolved = await resolveOtFont(fontSpec)
	if (resolved?.font) {
		try {
			const w = resolved.font.getAdvanceWidth(text, size)
			if (Number.isFinite(w) && w > 0) {
				measureStats.font++
				measureCache.set(key, w)
				return w
			}
		} catch { /* 落到浏览器度量 */ }
	}

	// 次选：浏览器度量（字体文件缺失或解析失败时）
	if (browser) {
		try {
			const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text id="t" style="font:${escapeCss(fontSpec)}">${escapeXml(text)}</text></svg>`
			const html = `<!DOCTYPE html><body>${svg}<script>document.title=document.getElementById('t').getComputedTextLength()</script></body>`
			const tmpFile = path.join(os.tmpdir(), `dv-measure-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.html`)
			await fs.promises.writeFile(tmpFile, html, "utf-8")
			try {
				const out = await capture(browser, ["--dump-dom", `file://${tmpFile}`])
				const m = out.match(/<title>([\d.]+)<\/title>/)
				const w = m ? Number(m[1]) : null
				if (w) {
					measureStats.browser++
					measureCache.set(key, w)
				}
				return w
			} finally {
				fs.promises.unlink(tmpFile).catch(() => {})
			}
		} catch { return null }
	}

	return null
}

async function capture(browser, extraArgs) {
	return new Promise((resolve, reject) => {
		const child = spawn(browser, ["--headless=new", "--disable-gpu", "--no-sandbox", ...extraArgs], { stdio: ["ignore", "pipe", "ignore"] })
		let stdout = ""
		child.stdout.on("data", d => { stdout += d.toString() })
		child.on("error", reject)
		child.on("close", code => code === 0 ? resolve(stdout) : reject(new Error(`exit ${code}`)))
	})
}

/**
 * 避免「孤字断行」：当某行只剩 1-2 个字、或下一行以标点开头时，
 * 把上一行末尾的字挪到下一行 / 把标点并回上一行，让断点更自然。
 */
async function tidyBreaks(lines, widthOf, maxWidthPx) {
	const arr = lines.map(l => [...l])
	for (let i = 1; i < arr.length; i++) {
		// 下一行以标点开头 → 标点回挂上一行（前提是不超宽）
		if (/^[，。！？；：、）】》”’%…]/.test(arr[i].join("")) && arr[i - 1].length > 2) {
			const merged = arr[i - 1].join("") + arr[i][0]
			if ((await widthOf(merged)) <= maxWidthPx * 1.02) arr[i].unshift(arr[i - 1].pop())
		}
		// 当前行只剩 1-2 字且上一行较满 → 从上一行借字
		if (arr[i].length <= 2 && arr[i - 1].length > 4) {
			const need = Math.min(arr[i - 1].length - 3, 3 - arr[i].length)
			for (let k = 0; k < need; k++) arr[i].unshift(arr[i - 1].pop())
		}
	}
	return arr.map(l => l.join("")).filter(Boolean)
}

/**
 * 生成单个分镜的 HTML 画面（交给无头浏览器截图）
 * @param {object} shot 分镜
 * @param {object} spec 规格
 * @param {object} ctx 上下文 { total, docTitle, browser }
 */
export async function buildShotHtml(shot, spec, ctx = {}) {
	const { width, height, theme, safeArea } = spec
	const f = cssFontStack(spec)
	const fs_ = theme.fontSize
	const innerWidth = width - safeArea.left - safeArea.right

	const isCover = shot.kind === "cover"
	const isCta = shot.kind === "cta"
	const isToc = shot.kind === "toc"
	const hero = isCover || isCta

	const title = shot.title || ctx.docTitle || ""
	// 屏显优先用 screenText；未填写时回退口播稿（模型常只补 narration），最后才是原文素材
	const body = shot.screenText || shot.narration || shot.sourceText || ""

	const titleSize = hero ? fs_.title : fs_.heading
	const bodySize = isToc ? Math.round(fs_.body * 1.1) : fs_.body
	// 折行可用宽度（像素）：卡片左右 padding 各 38px，标题/目录卡无额外缩进
	const cardInnerWidth = Math.max(200, innerWidth - 76)
	const browser = ctx.browser ?? null

	const titleLines = await wrapLines(title, innerWidth, hero ? 2 : 2, `${titleSize}px ${f}`, browser)
	const bodyLines = await wrapLines(body, cardInnerWidth, hero ? 3 : isToc ? 10 : 7, `${bodySize}px ${f}`, browser)

	const progress = Math.round(((shot.index || 1) / (ctx.total || 1)) * 100)
	const codeLines = shot.codeBlock
		? String(shot.codeBlock).split("\n").slice(0, spec.id === "portrait" ? 9 : 13)
		: []

	const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: ${width}px; height: ${height}px; overflow: hidden; }
  body {
    background: ${theme.background};
    color: ${theme.foreground};
    font-family: ${f};
    position: relative;
    -webkit-font-smoothing: antialiased;
  }
  .topbar { position: absolute; top: 0; left: 0; right: 0; height: ${Math.round(height * 0.008)}px; background: ${theme.accent}; }
  .glow { position: absolute; border-radius: 50%; background: ${theme.accentSoft}; opacity: .55; filter: blur(${hero ? 2 : 1}px); }
  .stage {
    position: absolute;
    left: ${safeArea.left}px; right: ${safeArea.right}px;
    top: ${safeArea.top}px; bottom: ${safeArea.bottom}px;
    display: flex; flex-direction: column; justify-content: ${hero ? "center" : "flex-start"};
  }
  h1 { font-size: ${titleSize}px; line-height: 1.24; font-weight: 700; letter-spacing: -0.5px; }
  h1.center { text-align: center; }
  .rule { width: ${Math.min(180, innerWidth * 0.14)}px; height: 7px; border-radius: 4px; background: ${theme.accent}; margin: ${hero ? 34 : 26}px 0; }
  .card {
    background: ${theme.cardBackground};
    border-radius: 18px;
    padding: 34px 38px;
    border-left: 6px solid ${theme.accent};
  }
  .card p { font-size: ${bodySize}px; line-height: 1.66; opacity: .95; }
  .card p + p { margin-top: ${isToc ? 18 : 2}px; }
  .toc-item { display: flex; align-items: baseline; gap: 18px; font-size: ${bodySize}px; line-height: 1.9; }
  .toc-no { color: ${theme.accent}; font-weight: 700; font-variant-numeric: tabular-nums; min-width: 2ch; }
  pre {
    margin-top: auto;
    background: #0B1220; border: 1.5px solid ${theme.accentSoft}; border-radius: 14px;
    padding: 26px 30px; font-size: ${Math.round(bodySize * 0.7)}px; line-height: 1.55;
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    color: #7DD3FC; white-space: pre-wrap; word-break: break-all;
  }
  .meta { position: absolute; left: ${safeArea.left}px; right: ${safeArea.right}px; bottom: ${Math.round(safeArea.bottom * 0.42)}px; }
  .meta span { font-size: ${fs_.caption}px; color: ${theme.muted}; }
  .bar { margin-top: 12px; height: 6px; border-radius: 3px; background: rgba(255,255,255,.1); overflow: hidden; }
  .bar i { display: block; height: 100%; width: ${progress}%; background: ${theme.accent}; }
</style>
</head>
<body>
  <div class="topbar"></div>
  ${hero ? `<div class="glow" style="width:${Math.round(height * 0.34)}px;height:${Math.round(height * 0.34)}px;top:-${Math.round(height * 0.08)}px;right:-${Math.round(height * 0.06)}px;"></div>` : ""}
  <div class="stage">
    <h1 class="${hero ? "center" : ""}">${escapeHtml(titleLines.join("<br>"))}</h1>
    ${hero ? "" : '<div class="rule"></div>'}
    ${isToc
	? `<div class="card">${bodyLines.filter(Boolean).map(line => {
		const m = String(line).match(/^(\d+)[.、]\s*(.*)$/)
		return m ? `<div class="toc-item"><span class="toc-no">${escapeHtml(m[1])}</span><span>${escapeHtml(m[2])}</span></div>`
			: `<div class="toc-item"><span class="toc-no">·</span><span>${escapeHtml(line)}</span></div>`
	}).join("")}</div>`
	: bodyLines.filter(Boolean).length
		? `<div class="card">${bodyLines.filter(Boolean).map(l => `<p>${escapeHtml(l)}</p>`).join("")}</div>`
		: ""}
    ${codeLines.length ? `<pre>${escapeHtml(codeLines.join("\n"))}</pre>` : ""}
  </div>
  ${hero ? "" : `<div class="meta"><span>${escapeHtml(ctx.docTitle || "")} ｜ ${shot.index || 1}/${ctx.total || 1}</span><div class="bar"><i></i></div></div>`}
</body>
</html>`

	return html
}

/** drawtext 降级模式下的单行文本切分（按字数估算） */
function plainLines(text, chars, maxLines) {
	const raw = String(text || "").replace(/[ \t]+/g, " ").trim()
	if (!raw) return []
	return wrapByChars(raw, chars, maxLines)
}

function escapeXml(text) {
	return String(text ?? "")
		.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;").replace(/'/g, "&apos;")
}

function escapeHtml(text) {
	return String(text ?? "")
		.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}


/**
 * 把分镜画面渲染为 PNG
 * 优先：无头浏览器截图（完整 CSS 排版）
 * 降级：ffmpeg 纯色底图 + drawtext 烧字（中文由系统字体渲染）
 * @returns {Promise<string>} 实际使用的渲染方式
 */
async function shotToPng(shot, spec, ctx, htmlPath, pngPath) {
	const browser = await findBrowser()
	if (browser) {
		try {
			// --window-size 在 macOS/Linux 下包含标题栏高度，若按规格尺寸传参会裁掉底部内容；
			// 这里加高窗口并用 crop 精确取顶部规格区域，保证版式不被切。
			await run(browser, [
				"--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
				"--disable-lcd-text", "--force-device-scale-factor=1",
				`--window-size=${spec.width},${spec.height + BROWSER_CHROME_EXTRA}`,
				`--screenshot=${pngPath}`,
				`file://${htmlPath}`
			], 30000)
			if (fs.existsSync(pngPath) && fs.statSync(pngPath).size > 2048) {
				await normalizeSize(pngPath, spec)
				return "browser"
			}
		} catch { /* 降级到 drawtext */ }
	}
	await drawTextFallback(shot, spec, ctx, pngPath)
	return "drawtext"
}

const BROWSER_CHROME_EXTRA = 120

/** 把截图归一化到规格尺寸（裁掉浏览器补高的部分） */
async function normalizeSize(pngPath, spec) {
	const tmpPath = `${pngPath}.norm.png`
	try {
		await run("ffmpeg", [
			"-y", "-loglevel", "error", "-i", pngPath,
			"-vf", `crop=${spec.width}:${spec.height}:0:0`,
			"-frames:v", "1", tmpPath
		], 60000)
		if (fs.existsSync(tmpPath) && fs.statSync(tmpPath).size > 1024) {
			await fs.promises.rename(tmpPath, pngPath)
		}
	} catch { /* 保留原图，后续仍会按 -vf 处理 */ }
	finally {
		try { if (fs.existsSync(tmpPath)) await fs.promises.unlink(tmpPath) } catch { /* 忽略 */ }
	}
}

/** 无浏览器时的降级渲染：色块底图 + drawtext 逐行烧字 */
async function drawTextFallback(shot, spec, ctx, pngPath) {
	const { width, height, theme, safeArea } = spec
	const fs_ = theme.fontSize
	const hero = shot.kind === "cover" || shot.kind === "cta"
	const titleSize = hero ? fs_.title : fs_.heading
	const bodySize = fs_.body
	const innerWidth = width - safeArea.left - safeArea.right

	const titleLines = plainLines(shot.title || ctx.docTitle || "", Math.floor(innerWidth / (titleSize * 1.05)), 2)
	const bodyLines = plainLines(shot.screenText || shot.narration || shot.sourceText || "", Math.floor(innerWidth / (bodySize * 1.05)), hero ? 3 : 6)

	const fontFile = pickCjkFont()
	const lines = []
	let y = safeArea.top + (hero ? Math.round(height * 0.34) : Math.round(height * 0.14))
	for (const line of titleLines) {
		lines.push({ text: line, size: titleSize, color: theme.foreground, y })
		y += Math.round(titleSize * 1.3)
	}
	y += hero ? 10 : 18
	for (const line of bodyLines) {
		lines.push({ text: line, size: bodySize, color: theme.foreground, y })
		y += Math.round(bodySize * 1.7)
	}
	lines.push({ text: `${ctx.docTitle || ""} ${shot.index || 1}/${ctx.total || 1}`, size: fs_.caption, color: theme.muted, y: height - Math.round(safeArea.bottom * 0.55) })

	const filters = lines.filter(l => l.text).map(l => {
		const parts = [`drawtext=text='${escapeDrawText(l.text)}'`]
		if (fontFile) parts.push(`fontfile='${escapeFilterValue(fontFile)}'`)
		parts.push(`fontsize=${l.size}`, `fontcolor=${hexToFFmpeg(l.color)}`, `x=${safeArea.left}`, `y=${l.y}`)
		return parts.join(":")
	})

	const args = ["-y", "-loglevel", "error", "-f", "lavfi", "-i", `color=c=${theme.background}:s=${width}x${height}`]
	if (filters.length) args.push("-vf", filters.join(","))
	args.push("-frames:v", "1", pngPath)
	await run("ffmpeg", args, 60000)
}

/** #RRGGBB -> 0xRRGGBB（ffmpeg 颜色写法） */
function hexToFFmpeg(color) {
	return String(color).startsWith("#") ? `0x${color.slice(1)}` : color
}

/** filtergraph 选项值转义：单引号包裹时内部 ' \ : 需转义 */
function escapeFilterValue(value) {
	return String(value).replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/:/g, "\\:")
}

function escapeDrawText(text) {
	return String(text).replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/:/g, "\\:").replace(/%/g, "\\%")
}

let cjkFontCache
/** 在系统中找一个可用的中文字体文件，供 drawtext 使用 */
function pickCjkFont() {
	if (cjkFontCache !== undefined) return cjkFontCache
	const candidates = [
		"/System/Library/Fonts/PingFang.ttc",
		"/System/Library/Fonts/Hiragino Sans GB.ttc",
		"/System/Library/Fonts/STHeiti Light.ttc",
		"/System/Library/Fonts/Supplemental/Songti.ttc",
		"/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
		"/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
		"C:\\Windows\\Fonts\\msyh.ttc"
	]
	cjkFontCache = candidates.find(p => fs.existsSync(p)) || null
	return cjkFontCache
}

/** 统一的命令执行入口：名字（ffmpeg）会自动解析为绝对路径，绝对路径原样使用 */
function run(cmd, args, timeoutMs = 180000) {
	return new Promise((resolve, reject) => {
		const resolved = path.isAbsolute(cmd) ? cmd : resolveBinary(cmd)
		if (!resolved) {
			return reject(new Error(`未找到可执行文件「${cmd}」。请先安装 ffmpeg（macOS：brew install ffmpeg；Windows：winget install Gyan.FFmpeg），或用环境变量 FFMPEG_PATH 指定其绝对路径。`))
		}
		runBinary(resolved, args, { timeoutMs })
			.then(result => {
				if (result.code === 0) resolve()
				else reject(new Error(`${path.basename(cmd)} 退出码 ${result.code}：${result.stderr.trim().slice(0, 400)}`))
			})
			.catch(error => {
				if (/超时/.test(error.message)) reject(new Error(`${path.basename(cmd)} 执行超时（${Math.round(timeoutMs / 1000)} 秒）`))
				else reject(error)
			})
	})
}

/**
 * 渲染成片
 * @param {object} params
 * @param {object} params.plan 渲染计划（含 shots / spec / audioClips）
 * @param {string} params.outDir 输出目录
 * @param {function} [params.onProgress] 进度回调 (percent, stage, detail)
 */
export async function render({ plan, outDir, onProgress = () => {} } = {}) {
	const { shots = [], spec, audioClips = [], docTitle = "" } = plan
	if (!spec) throw new Error("渲染计划缺少 spec（规格参数）")
	if (!shots.length) throw new Error("渲染计划缺少 shots（分镜脚本）")

	const ffmpegCheck = await detectFfmpeg()
	if (!ffmpegCheck.available) throw new Error(ffmpegCheck.reason)

	// 折行测宽与截图共用同一浏览器，保证字体渲染一致
	const renderBrowser = await findBrowser()

	const framesDir = path.join(outDir, "frames")
	const clipsDir = path.join(outDir, "clips")
	await fs.promises.mkdir(framesDir, { recursive: true })
	await fs.promises.mkdir(clipsDir, { recursive: true })

	const audioMap = new Map(audioClips.map(c => [c.index, c]))
	const clipPaths = []
	const total = shots.length
	const renderModes = new Set()
	let trimmed = 0

	// 渲染前置校验：既没有浏览器也没有可用的中文字体时，宁可明确失败也不要产出空白成片
	if (!(await findBrowser()) && !pickCjkFont()) {
		throw new Error("无法渲染画面：未检测到 Chrome/Edge/Chromium，且系统缺少可用中文字体（drawtext 降级也需要字体）。请安装浏览器或中文字体后重试。")
	}

	// 第 1 阶段：生成每个分镜的画面并合成为带音轨的分段视频（约 70% 工作量）
	for (let i = 0; i < shots.length; i++) {
		const shot = shots[i]
		const audio = audioMap.get(shot.index)
		const duration = Math.max(1.5, audio?.durationSec || shot.durationSec || 4)

		const base = path.join(framesDir, `shot-${String(shot.index).padStart(3, "0")}`)
		const htmlPath = `${base}.html`
		const pngPath = `${base}.png`
		const clipPath = path.join(clipsDir, `clip-${String(shot.index).padStart(3, "0")}.mp4`)

		await fs.promises.writeFile(htmlPath, await buildShotHtml(shot, spec, { total, docTitle, browser: renderBrowser }), "utf-8")
		const mode = await shotToPng(shot, spec, { total, docTitle }, htmlPath, pngPath)
		renderModes.add(mode)

		if (!fs.existsSync(pngPath) || fs.statSync(pngPath).size < 1024) {
			throw new Error(`分镜 ${shot.index} 画面生成失败（${mode} 模式未产出有效图片），请检查浏览器或 ffmpeg 的 drawtext 滤镜是否可用`)
		}

		const filters = [`fps=${spec.fps}`, "format=yuv420p"]

		const args = ["-y", "-loglevel", "error", "-loop", "1", "-i", pngPath]
		if (audio?.file && fs.existsSync(audio.file)) {
			args.push("-i", audio.file)
		} else {
			args.push("-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo")
		}
		args.push(
			"-t", String(duration),
			"-vf", filters.join(","),
			// apad 把音频无限垫静音，配合输出端 -t 精确截断。
			// 不能用 -shortest：AAC 编码器首包延迟会让超短 MP3（约 1~3 秒）的整条音轨被丢弃
			"-af", "apad",
			"-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
			"-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
			clipPath
		)
		await run("ffmpeg", args)
		clipPaths.push(clipPath)
		onProgress(Math.round(((i + 1) / total) * 70), "render", `已渲染分镜 ${i + 1}/${total}`)
	}

	// 第 2 阶段：拼接（约 20% 工作量）
	const listFile = path.join(outDir, "concat.txt")
	await fs.promises.writeFile(listFile, clipPaths.map(p => `file '${p.replace(/'/g, "'\\''")}'`).join("\n"), "utf-8")
	const mergedPath = path.join(outDir, "merged.mp4")
	await run("ffmpeg", [
		"-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listFile,
		"-c", "copy", mergedPath
	])
	onProgress(90, "concat", "分段拼接完成")

	// 第 3 阶段：转封装输出（约 10% 工作量）
	const finalName = `${sanitize(docTitle || "讲解视频")}-${spec.id}-${spec.width}x${spec.height}.mp4`
	const finalPath = path.join(outDir, finalName)
	await run("ffmpeg", [
		"-y", "-loglevel", "error", "-i", mergedPath,
		"-c", "copy", "-movflags", "+faststart", finalPath
	])
	onProgress(98, "finalize", "正在生成最终文件")

	const stat = await fs.promises.stat(finalPath)
	const durationSec = shots.reduce((n, s) => n + Math.max(1.5, audioMap.get(s.index)?.durationSec || s.durationSec || 4), 0)

	onProgress(100, "done", "渲染完成")

	return {
		output: finalPath,
		fileName: finalName,
		sizeBytes: stat.size,
		sizeText: `${(stat.size / 1024 / 1024).toFixed(2)} MB`,
		durationSec: Math.round(durationSec * 10) / 10,
		resolution: `${spec.width}x${spec.height}`,
		fps: spec.fps,
		shotCount: shots.length,
		hasAudio: audioClips.some(a => a.file),
		renderMode: [...renderModes].join("+") || "browser",
		trimmedFrames: trimmed
	}
}

function sanitize(name) {
	return String(name).replace(/[\\/:*?"<>|\s]+/g, "-").slice(0, 50)
}

export { escapeXml }
