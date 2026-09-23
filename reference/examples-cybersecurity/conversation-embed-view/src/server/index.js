#!/usr/bin/env node

import path from "node:path"
import express from "express"
import { submitForm } from "./handlers/submit-form.js"

const app = express()

// 开发环境请求首页时触发 index.html 重新编译
if (process.env.NODE_ENV !== "production") {
  app.use((req, res, next) => {
    if (req.path !== "/") {
      return next()
    }
    console.time("compile index.html")
    Bun.build({
      production: false,
      entrypoints: ["src/client/index.html"],
      outdir: "./public",
      plugins: [require("bun-plugin-tailwind").default],
      minify: false,
    }).finally(() => {
      console.timeEnd("compile index.html")
      next()
    })
  })
}

app.use(express.json())
app.use(express.static(path.join(
  import.meta.dirname, process.env.NODE_ENV === "production"
    ? "public"
    : "../../public"
)))

// 示例 API：处理表单提交
app.post("/api/submit", submitForm)

// 监听端口 0，由系统随机分配
app.listen(process.env.NODE_ENV === "production" ? 0 : 8000, function () {
  console.log(JSON.stringify({
    "type": "http_start",
    "port": this.address().port
  }))
})

// 优雅退出
process.on("SIGINT", async () => {
  console.log("Server shutdown complete")
  process.exit(0)
})