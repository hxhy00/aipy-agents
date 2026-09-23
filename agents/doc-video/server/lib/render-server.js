/**
 * 独立渲染服务端：异步任务队列 + HTTP 接口。
 *
 * 为什么单独拆一个服务端：
 *   一个 3 分钟的横屏讲解视频，配音合成 + 逐帧渲染 + 拼接通常需要数分钟。
 *   如果直接在 MCP 工具里同步执行，会阻塞整个对话轮次，用户只能干等，也容易触发超时。
 *   因此这里把渲染下沉为独立进程内的异步任务：
 *     提交任务（毫秒级返回 taskId） → 后台排队渲染 → 工具随时查询进度 → 完成后取产物
 *   任务状态同时落盘（tasks/<taskId>.json），即使服务重启也能读到历史任务。
 */

import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import http from "node:http"
import { synthesize } from "./tts.js"
import { render } from "./renderer.js"

/**
 * 渲染并发度：默认按 CPU 核数的一半自适应（至少 1）。
 * 渲染是「浏览器截图 + ffmpeg 合成」的混合负载，既吃 CPU 也吃内存，
 * 全核并行反而会因为内存争抢变慢，取半数核数更稳。
 * 仍可通过 VIDEO_RENDER_CONCURRENCY 显式覆盖。
 */
function defaultConcurrency() {
	const cores = os.cpus()?.length || 2
	return Math.max(1, Math.floor(cores / 2))
}

const TASKS = new Map()
let server = null
let serverUrl = ""
let workDir = ""
let concurrency = 1
let running = 0
const queue = []

function nowIso() {
	return new Date().toISOString()
}

function taskFile(id) {
	return path.join(workDir, "tasks", `${id}.json`)
}

async function persist(task) {
	try {
		await fs.promises.mkdir(path.join(workDir, "tasks"), { recursive: true })
		const { plan, ...rest } = task
		await fs.promises.writeFile(taskFile(task.id), JSON.stringify({
			...rest,
			plan: plan ? { spec: plan.spec, shotCount: plan.shots?.length, docTitle: plan.docTitle } : null
		}, null, 2), "utf-8")
	} catch { /* 落盘失败不影响主流程 */ }
}

/** 确保渲染服务端已启动（懒启动，监听随机端口） */
export async function ensureServer() {
	if (server) return { url: serverUrl, workDir, concurrency }

	const configuredPort = Number(process.env.VIDEO_RENDER_PORT || 0)
	workDir = process.env.VIDEO_RENDER_DIR
		? path.resolve(process.env.VIDEO_RENDER_DIR)
		: path.join(process.cwd(), "doc-video-output")
	concurrency = Math.max(1, Number(process.env.VIDEO_RENDER_CONCURRENCY) || defaultConcurrency())
	await fs.promises.mkdir(workDir, { recursive: true })

	server = http.createServer(handleRequest)
	await new Promise((resolve, reject) => {
		server.once("error", reject)
		server.listen(configuredPort, "127.0.0.1", resolve)
	})
	const addr = server.address()
	serverUrl = `http://127.0.0.1:${addr.port}`
	console.log(JSON.stringify({ type: "render_server_start", port: addr.port, workDir }))
	return { url: serverUrl, workDir, concurrency }
}

export function getServerInfo() {
	return { running: Boolean(server), url: serverUrl, workDir, concurrency, queued: queue.length, running }
}

/** HTTP 接口：供外部脚本或前端页面查询任务 */
function handleRequest(req, res) {
	const send = (code, data) => {
		res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" })
		res.end(JSON.stringify(data))
	}
	const url = new URL(req.url, "http://localhost")

	if (url.pathname === "/health") {
		return send(200, { ok: true, ...getServerInfo() })
	}

	if (url.pathname === "/tasks" && req.method === "GET") {
		return send(200, { tasks: [...TASKS.values()].map(t => summarize(t)) })
	}

	const taskMatch = url.pathname.match(/^\/tasks\/([\w-]+)$/)
	if (taskMatch && req.method === "GET") {
		const task = TASKS.get(taskMatch[1])
		if (!task) return send(404, { error: "任务不存在" })
		return send(200, summarize(task))
	}

	return send(404, { error: "未知接口", available: ["/health", "/tasks", "/tasks/{taskId}"] })
}

/**
 * 提交渲染任务（立即返回，不阻塞）
 * @param {object} params
 * @param {object} params.plan 渲染计划
 * @param {object} params.spec 规格
 */
export async function submitTask({ plan, spec, docTitle = "" }) {
	const info = await ensureServer()
	const id = `rv${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
	const taskDir = path.join(workDir, id)

	const task = {
		id,
		status: "queued",
		stage: "queued",
		progress: 0,
		detail: "已进入渲染队列",
		spec: spec.id,
		specName: spec.name,
		resolution: `${spec.width}x${spec.height}`,
		docTitle,
		shotCount: plan.shots?.length || 0,
		estimatedDurationSec: plan.shots?.reduce((n, s) => n + (s.durationSec || 0), 0) || 0,
		outputDir: taskDir,
		createdAt: nowIso(),
		updatedAt: nowIso(),
		startedAt: null,
		finishedAt: null,
		result: null,
		error: null,
		audio: null,
		logs: [],
		_plan: plan
	}

	TASKS.set(id, task)
	await persist(task)
	queue.push(id)
	pump()

	return { taskId: id, serverUrl: info.url, outputDir: taskDir, status: task.status, queuePosition: queue.indexOf(id) + 1 }
}

function log(task, message) {
	task.logs.push(`${new Date().toISOString().slice(11, 19)} ${message}`)
	if (task.logs.length > 200) task.logs.shift()
}

/** 队列泵：按并发度调度任务 */
function pump() {
	while (running < concurrency && queue.length) {
		const id = queue.shift()
		const task = TASKS.get(id)
		if (!task) continue
		running++
		runTask(task)
			.catch(error => {
				task.status = "failed"
				task.error = error?.message || String(error)
				task.detail = `渲染失败：${task.error}`
				log(task, `失败：${task.error}`)
			})
			.finally(async () => {
				running--
				task.finishedAt = task.finishedAt || nowIso()
				task.updatedAt = nowIso()
				await persist(task)
				pump()
			})
	}
}

async function runTask(task) {
	task.status = "running"
	task.stage = "audio"
	task.progress = 2
	task.detail = "正在合成配音"
	task.startedAt = nowIso()
	log(task, "任务开始，进入配音合成阶段")
	await persist(task)

	const plan = task._plan
	const spec = plan.spec
	const audioDir = path.join(task.outputDir, "audio")
	const isLong = task.estimatedDurationSec > 120

	// 阶段一：配音合成（0-15%）
	try {
		const tts = await synthesize({
			shots: plan.shots,
			voice: process.env.VIDEO_EDGE_TTS_VOICE || plan.voice || "zh-CN-XiaoxiaoNeural",
			rate: plan.ttsRate || spec.ttsRate,
			outDir: audioDir
		})
		plan.audioClips = tts.clips
		task.audio = { engine: tts.engine, voice: tts.voice, totalDurationSec: tts.totalDurationSec, errors: tts.errors }
		log(task, `配音完成：引擎 ${tts.engine}，共 ${tts.clips.length} 段，合计 ${tts.totalDurationSec} 秒`)
		if (tts.errors.length) tts.errors.forEach(e => log(task, e))
	} catch (error) {
		task.audio = { engine: "none", error: error.message }
		plan.audioClips = plan.shots.map(s => ({ index: s.index, file: null, durationSec: s.durationSec, silent: true }))
		log(task, `配音合成异常，降级为静音音轨：${error.message}`)
	}
	task.progress = 15
	task.stage = "render"
	task.detail = "配音完成，开始渲染画面"
	await persist(task)

	// 阶段二：渲染（15-95%）
	const result = await render({
		plan,
		outDir: task.outputDir,
		onProgress: (percent, stage, detail) => {
			task.progress = 15 + Math.round(percent * 0.8)
			task.stage = stage
			task.detail = `${detail}${isLong ? "（长视频渲染较慢，请耐心等待）" : ""}`
			task.updatedAt = nowIso()
			if (task.progress % 10 === 0) log(task, task.detail).valueOf()
		}
	})

	task.status = "succeeded"
	task.stage = "done"
	task.progress = 100
	task.detail = "渲染完成"
	task.result = result
	task.updatedAt = nowIso()
	log(task, `渲染完成：${result.output}（${result.sizeText}，${result.durationSec} 秒）`)
}

/** 查询任务（轻量摘要，避免把庞大的 plan 回传给对话） */
export function getTask(id) {
	const task = TASKS.get(id)
	if (task) return summarize(task, true)
	return readTaskFromDisk(id)
}

async function readTaskFromDisk(id) {
	try {
		const raw = await fs.promises.readFile(taskFile(id), "utf-8")
		const data = JSON.parse(raw)
		return { ...data, fromDisk: true }
	} catch {
		return null
	}
}

function summarize(task, withLogs = false) {
	const out = {
		taskId: task.id,
		status: task.status,
		stage: task.stage,
		progress: task.progress,
		detail: task.detail,
		spec: task.spec,
		specName: task.specName,
		resolution: task.resolution,
		shotCount: task.shotCount,
		estimatedDurationSec: task.estimatedDurationSec,
		outputDir: task.outputDir,
		createdAt: task.createdAt,
		startedAt: task.startedAt,
		finishedAt: task.finishedAt,
		elapsedSec: task.startedAt ? Math.round((Date.now() - new Date(task.startedAt).getTime()) / 1000) : 0,
		audio: task.audio,
		result: task.result,
		error: task.error
	}
	if (withLogs) out.logs = (task.logs || []).slice(-25)
	return out
}

/** 取消排队中的任务 */
export function cancelTask(id) {
	const task = TASKS.get(id)
	if (!task) return { ok: false, reason: "任务不存在" }
	if (task.status === "queued") {
		const idx = queue.indexOf(id)
		if (idx >= 0) queue.splice(idx, 1)
		task.status = "cancelled"
		task.detail = "已取消（尚未开始渲染）"
		task.finishedAt = nowIso()
		persist(task)
		return { ok: true, status: "cancelled" }
	}
	if (task.status === "running") {
		return { ok: false, reason: "任务已在渲染中，无法取消；可等待完成或直接丢弃该任务" }
	}
	return { ok: false, reason: `任务当前状态为 ${task.status}，无需取消` }
}

export function listTasks() {
	return [...TASKS.values()].map(t => summarize(t))
}

/** 关闭服务端（进程退出时调用） */
export async function closeServer() {
	if (!server) return
	await new Promise(resolve => server.close(resolve))
	server = null
}
