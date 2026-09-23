/**
 * MCP 协议层校验：启动服务端 → initialize 握手 → tools/list → prompts/list → 关闭
 */
import { spawn } from "node:child_process"

const child = spawn("node", ["server/index.js"], { cwd: import.meta.dirname, stdio: ["ignore", "pipe", "pipe"] })
let port = 0
let buf = ""
let failed = false

const cleanup = (code = 0) => {
	try { child.kill() } catch { /* 忽略 */ }
	setTimeout(() => process.exit(code), 200)
}

child.stdout.on("data", chunk => {
	buf += chunk.toString()
	const m = buf.match(/\{"type":"http_start","port":(\d+)\}/)
	if (m && !port) {
		port = Number(m[1])
		run()
	}
})
child.stderr.on("data", c => {
	const s = c.toString()
	if (!/Warning|trace-warnings/.test(s)) process.stderr.write("[server] " + s)
})

const rpc = async (method, params, id = 1) => {
	const res = await fetch(`http://127.0.0.1:${port}/mcp`, {
		method: "POST",
		headers: { "Content-Type": "application/json", "Accept": "application/json, text/event-stream" },
		body: JSON.stringify({ jsonrpc: "2.0", id, method, params })
	})
	const text = await res.text()
	const line = text.split("\n").find(l => l.startsWith("data:"))
	const payload = line ? line.slice(5).trim() : text
	try { return JSON.parse(payload) } catch { return { raw: text.slice(0, 400) } }
}

async function run() {
	try {
		console.log(`✔ 服务端已启动，端口 ${port}`)

		const init = await rpc("initialize", {
			protocolVersion: "2025-06-18",
			capabilities: {},
			clientInfo: { name: "protocol-check", version: "1.0" }
		})
		if (init.result?.serverInfo) {
			console.log(`✔ initialize 握手成功：${init.result.serverInfo.name} v${init.result.serverInfo.version}`)
		} else {
			console.log("✘ initialize 失败：", JSON.stringify(init).slice(0, 300)); failed = true
		}

		const tools = await rpc("tools/list", {}, 2)
		const names = (tools.result?.tools || []).map(t => t.name)
		if (names.length === 5) {
			console.log(`✔ tools/list 返回 ${names.length} 个工具：${names.join(", ")}`)
		} else {
			console.log(`✘ 工具数异常（期望 5，实际 ${names.length}）：${names.join(", ")}`); failed = true
		}

		const prompts = await rpc("prompts/list", {}, 3)
		const pnames = (prompts.result?.prompts || []).map(p => p.name)
		pnames.includes("addition-system-instruction")
			? console.log(`✔ prompts/list 返回：${pnames.join(", ")}`)
			: (console.log(`✘ 缺少系统提示词，实际：${pnames.join(", ")}`), failed = true)

		console.log(failed ? "\n协议层校验存在失败项 ✘" : "\n协议层校验全部通过 ✔")
		cleanup(failed ? 1 : 0)
	} catch (err) {
		console.log("✘ 校验异常：", err.message)
		cleanup(1)
	}
}

setTimeout(() => { console.log("✘ 超时未启动"); cleanup(1) }, 25000)
