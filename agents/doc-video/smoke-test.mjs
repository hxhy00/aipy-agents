// 讲解视频智能体端到端冒烟测试：文档解析 → 双规格规划 → 文案补齐 → 质检 → 异步渲染 → 状态轮询
import { handler as readDoc } from "./server/tools/read-document.js"
import { handler as planVideo } from "./server/tools/plan-video.js"
import { handler as inspectScript } from "./server/tools/inspect-script.js"
import { handler as submitRender } from "./server/tools/submit-render.js"
import { handler as renderStatus } from "./server/tools/render-status.js"

const DOC = decodeURIComponent(new URL("./sample-doc.md", import.meta.url).pathname)
const OUT = "/tmp/dv-out"

const line = t => console.log("\n=== " + t + " ===")
const ok = m => console.log("  ✔ " + m)
const fail = m => { console.log("  ✘ " + m); process.exitCode = 1 }

line("textWidth 字体度量（opentype.js）")
const { textWidth, measureStats } = await import("./server/lib/renderer.js")
const widthCn = await textWidth("行业调研报告", "16px \"PingFang SC\"", null)
const widthLatin = await textWidth("Helloworld", "16px \"PingFang SC\"", null)
console.log(`  中文字宽 ${widthCn} ｜ 拉丁字宽 ${widthLatin} ｜ 度量字体 ${measureStats.lastFontFile || "（未命中）"}`)
if (measureStats.font > 0 && !measureStats.browser) {
	ok("字体文件度量生效，未回落到浏览器进程")
} else {
	fail(`度量降级了（font=${measureStats.font} browser=${measureStats.browser}）`)
}
// 中文等宽字体下，6 个汉字 @16px 应约等于 96px（误差 ±8%）
if (widthCn && Math.abs(widthCn - 96) / 96 < 0.08) ok(`中文字宽准确：${widthCn} ≈ 96px`)
else fail(`中文字宽异常：${widthCn}，期望约 96px`)

line("read_document")
const doc = await readDoc({ source: DOC })
const sections = doc.structuredContent.sections
console.log(doc.content[0].text.slice(0, 800))

line("plan_video (landscape)")
const planL = await planVideo({ spec: "landscape", docTitle: doc.structuredContent.title, sections })
const shotsL = planL.structuredContent?.shots ?? []
console.log(planL.content[0].text.slice(-600))
console.log("shots:", shotsL.length)

for (const s of shotsL) {
	s.narration = s.screenText || s.sourceText
}

line("inspect_script")
const qc = await inspectScript({ shots: shotsL, spec: "landscape" })
console.log(qc.content[0].text.slice(0, 500))
console.log("passed:", qc.structuredContent?.passed, "score:", qc.structuredContent?.score)

line("submit_render")
const sub = await submitRender({ spec: "landscape", shots: shotsL, docTitle: doc.structuredContent.title })
console.log(sub.content[0].text.slice(0, 700))
const taskId = sub.structuredContent?.taskId
if (!taskId) throw new Error("no taskId")

line("poll status")
let final = null
for (let i = 0; i < 100; i++) {
	await new Promise(r => setTimeout(r, 3000))
	final = await renderStatus({ taskId })
	const s = final.structuredContent
	console.log(`[${i}] ${s.status} ${s.progress}% ${s.detail ?? ""}`)
	if (s.status === "succeeded" || s.status === "failed") break
}
console.log("\n=== 最终状态 ===")
console.log(final.content[0].text)
