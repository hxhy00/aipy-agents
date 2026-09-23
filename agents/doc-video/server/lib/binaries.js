/**
 * 外部二进制解析层：ffmpeg / ffprobe 的定位与调用。
 *
 * 背景（为什么需要这一层）：
 *   插件由 GUI 宿主拉起，进程 PATH 往往只有系统默认值（macOS 下是 /usr/bin:/bin:/usr/sbin:/sbin），
 *   不含 /opt/homebrew/bin 这类包管理器目录。于是「终端里 ffmpeg 明明可用，插件内却报未检测到」。
 *
 * 解析优先级：
 *   1. 环境变量覆盖（FFMPEG_PATH / FFPROBE_PATH）—— 便于用户自定义与排查
 *   2. 随插件分发的内置二进制 vendor/<platform>-<arch>/ —— 若发布包内置则免安装（当前发布版不内置，见下）
 *   3. 系统 PATH
 *   4. 常见绝对路径（Homebrew / MacPorts / /usr/local / Windows 常见安装位置）
 *
 * 关于「不内置 ffmpeg」的决策（2026-09）：
 *   三平台全量 ffmpeg 约 126MB，打进单个 .mcpb 后会超过 GitHub Release 单文件 100MB 硬限制，
 *   也无法正常入库分发。因此发布包不再内置，改由用户自行安装（brew / winget），
 *   第 2 步的查找逻辑保留：本地开发时把二进制放进 vendor/ 仍可自动命中，无需改代码。
 *
 * 结果按命令名缓存，避免重复探测；探测失败不缓存，便于用户装完 ffmpeg 后无需重启即可生效。
 */

import fs from "node:fs"
import path from "node:path"
import os from "node:os"
import zlib from "node:zlib"
import { spawn } from "node:child_process"

/** 二进制文件名：Windows 需要 .exe 后缀 */
const EXE = process.platform === "win32" ? ".exe" : ""

/**
 * Windows 二进制以 .gz 形式随包分发（未压缩约 28MB / 个，压缩后约 29MB 总量减半）。
 * dxt 打包器（Bun 的 zip 实现）在 Windows 上不会保留可执行位，Node 又无法执行 .gz，
 * 因此首次解析时惰性解压到用户级缓存目录 ~/.aipy/bin，避免解压到插件目录触发签名/只读问题。
 */
function windowsCacheDir() {
	const dir = path.join(os.homedir(), ".aipy", "bin")
	fs.mkdirSync(dir, { recursive: true })
	return dir
}

/** 解压内置的 .gz 二进制，返回解压后的绝对路径；失败返回 null */
function decompressGz(gzPath, name) {
	try {
		const dir = windowsCacheDir()
		const out = path.join(dir, `${name}${EXE}`)
		// 已解压且体积合理则直接复用（不同版本差异由体积粗略判断，够用）
		if (fs.existsSync(out) && fs.statSync(out).size > 1024 * 1024) return out
		const buf = zlib.gunzipSync(fs.readFileSync(gzPath))
		if (buf.length < 1024 * 1024) return null
		const tmp = `${out}.tmp`
		fs.writeFileSync(tmp, buf)
		fs.renameSync(tmp, out)
		return out
	} catch {
		return null
	}
}

/**
 * 随插件分发目录的候选位置。
 * - 打包后：server.js 与 vendor/ 同级（dxt 包根目录）
 * - 开发态：server/lib/binaries.js → ../../vendor
 */
function vendorRoots() {
	const roots = []
	const dirs = [import.meta.dirname, process.cwd()]
	for (const dir of dirs) {
		if (!dir) continue
		roots.push(
			path.join(dir, "vendor"),
			path.join(dir, "..", "vendor"),
			path.join(dir, "..", "..", "vendor"),
			path.join(dir, "..", "..", "..", "vendor")
		)
	}
	return [...new Set(roots)]
}

/** 当前平台 + 架构的标识，例如 darwin-arm64 / win32-x64 */
export function platformTag() {
	const arch = process.arch === "arm64" ? "arm64" : "x64"
	return `${process.platform}-${arch}`
}

/** 内置二进制的候选路径（按平台架构子目录 + 扁平目录两种布局） */
function vendorCandidates(name) {
	const tag = platformTag()
	const file = `${name}${EXE}`
	const out = []
	// 目录顺序即优先级：离 server.js 越近的 vendor 越优先，避免误命中项目根目录下的无关目录
	for (const root of vendorRoots()) {
		out.push(path.join(root, tag, file))
		out.push(path.join(root, file))
	}
	return out
}

/** 系统常见安装路径 */
function systemCandidates(name) {
	const file = `${name}${EXE}`
	if (process.platform === "win32") {
		const pf = process.env["ProgramFiles"] || "C:\\Program Files"
		const pf86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)"
		return [
			path.join(pf, "ffmpeg", "bin", file),
			path.join(pf86, "ffmpeg", "bin", file),
			path.join(process.env.LOCALAPPDATA || "", "ffmpeg", "bin", file),
			// winget / chocolatey / scoop 常见落地位置
			path.join(process.env.LOCALAPPDATA || "", "Microsoft", "WinGet", "Links", file),
			path.join(process.env.USERPROFILE || "", "scoop", "shims", file),
			"C:\\ffmpeg\\bin\\" + file,
			"C:\\ProgramData\\chocolatey\\bin\\" + file
		]
	}
	const home = os.homedir()
	return [
		"/opt/homebrew/bin/" + file,
		"/usr/local/bin/" + file,
		"/opt/local/bin/" + file,
		"/usr/bin/" + file,
		"/snap/bin/" + file,
		path.join(home, ".local", "bin", file),
		path.join(home, "bin", file),
		path.join(home, ".aipy", "bin", file)
	]
}

/** 判断路径是否为可执行文件（存在 + 是文件 + 有执行位或 Windows 的 exe 后缀） */
function isExecutable(file) {
	try {
		if (!file || !fs.existsSync(file)) return false
		const stat = fs.statSync(file)
		if (!stat.isFile()) return false
		if (process.platform === "win32") return /\.(exe|bat|cmd)$/i.test(file)
		// 内置二进制若因解压丢失执行位，这里主动补回，避免「文件在但无法执行」
		if ((stat.mode & 0o111) === 0) {
			try { fs.chmodSync(file, 0o755) } catch { return false }
		}
		return true
	} catch {
		return false
	}
}

/** 从 PATH 里查找可执行文件（自行解析，不依赖 spawn("which") 以避免 PATH 本身缺失） */
function searchPath(name) {
	const raw = process.env.PATH || ""
	const dirs = raw.split(path.delimiter).filter(Boolean)
	for (const dir of dirs) {
		const candidate = path.join(dir, `${name}${EXE}`)
		if (isExecutable(candidate)) return candidate
	}
	return null
}

const cache = new Map()

/**
 * 解析某个命令的绝对路径。找不到返回 null。
 * @param {string} name 命令名，如 ffmpeg / ffprobe
 */
export function resolveBinary(name) {
	const upper = name.toUpperCase()
	const envOverride = String(process.env[`${upper}_PATH`] || "").trim()
	if (envOverride && isExecutable(envOverride)) return envOverride
	if (envOverride && !isExecutable(envOverride)) return null

	if (cache.has(name)) return cache.get(name)

	// 内置 > 系统 PATH > 常见绝对路径
	const builtin = builtinAvailable(name)
	const found = builtin || searchPath(name) || systemCandidates(name).find(isExecutable) || null

	if (found) cache.set(name, found)
	return found
}

/** 内置二进制是否就位（用于状态展示与诊断）：先找可直接执行的，再找 .gz 解压后的 */
export function builtinAvailable(name) {
	const direct = vendorCandidates(name).find(isExecutable)
	if (direct) return direct
	for (const candidate of vendorCandidates(name)) {
		const gz = `${candidate}.gz`
		if (fs.existsSync(gz)) {
			const out = decompressGz(gz, name)
			if (out && isExecutable(out)) return out
		}
	}
	return null
}

/** 清除解析缓存（例如用户中途安装 ffmpeg 后强制重探） */
export function clearBinaryCache() {
	cache.clear()
}

/**
 * 执行外部命令：自动解析绝对路径，避免 PATH 依赖。
 * 传入名字（ffmpeg）或绝对路径（/opt/homebrew/bin/ffmpeg）均可。
 * @returns {Promise<{code:number,stdout:string,stderr:string}>}
 */
export function runBinary(nameOrPath, args = [], { timeoutMs = 180000, cwd } = {}) {
	const resolved = path.isAbsolute(nameOrPath) ? nameOrPath : resolveBinary(nameOrPath)
	if (!resolved) {
		return Promise.reject(new Error(`未找到可执行文件「${nameOrPath}」。请在插件设置中指定路径，或安装 ffmpeg 后重试。`))
	}
	return new Promise((resolve, reject) => {
		let child
		try {
			child = spawn(resolved, args, { stdio: ["ignore", "pipe", "pipe"], cwd })
		} catch (error) {
			return reject(error)
		}
		let stdout = ""
		let stderr = ""
		const timer = setTimeout(() => {
			child.kill()
			reject(new Error(`${nameOrPath} 执行超时（${Math.round(timeoutMs / 1000)} 秒）`))
		}, timeoutMs)
		child.stdout?.on("data", d => { stdout += d.toString() })
		child.stderr?.on("data", d => { stderr += d.toString() })
		child.on("error", error => {
			clearTimeout(timer)
			reject(error)
		})
		child.on("close", code => {
			clearTimeout(timer)
			resolve({ code, stdout, stderr })
		})
	})
}

/**
 * 探测命令是否可用（探针用绝对路径，彻底摆脱 PATH）。
 * @returns {Promise<boolean>}
 */
export async function commandAvailable(name, args = ["-version"]) {
	const resolved = resolveBinary(name)
	if (!resolved) return false
	try {
		const res = await runBinary(resolved, args, { timeoutMs: 8000 })
		return res.code === 0
	} catch {
		return false
	}
}

/** 供状态展示：列出解析结果与来源，便于用户自助排查 */
export function describeBinaries() {
	const describe = name => {
		const envKey = `${name.toUpperCase()}_PATH`
		const envOverride = String(process.env[envKey] || "").trim()
		if (envOverride) {
			return { name, path: isExecutable(envOverride) ? envOverride : null, source: "env", envKey, envValue: envOverride }
		}
		// 复用 resolveBinary 的顺序（内置 → PATH → 常见路径），保证与真实执行一致
		const resolved = resolveBinary(name)
		if (!resolved) return { name, path: null, source: "missing" }
		if (builtinAvailable(name) === resolved) return { name, path: resolved, source: "builtin" }
		if (searchPath(name) === resolved) return { name, path: resolved, source: "path" }
		return { name, path: resolved, source: "system" }
	}
	return {
		platform: platformTag(),
		vendorDirs: vendorRoots(),
		ffmpeg: describe("ffmpeg"),
		ffprobe: describe("ffprobe")
	}
}
