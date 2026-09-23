# 文档一键成片（doc-video）

把文档变成讲解视频的 AiPy 智能体扩展。支持横屏知识讲解（1920x1080）与竖屏短视频（1080x1920）两种规格。

## 它解决什么问题

把一份 Word / Markdown / PDF 丢进 AiPy 对话框，产出可直接发布的讲解视频。拆成三层职责，避免一个环节出错拖垮整条链路：

| 层 | 谁来做 | 产出 |
|----|--------|------|
| 文案策划 | AI（`plan_video`） | 分镜脚本：每段旁白与画面提示 |
| 质检 | AI + 脚本（`inspect_script`） | 脚本合规性检查与修正建议 |
| 渲染 | 独立服务端（`submit_render` / `render_status`） | mp4 视频文件 |

渲染是长耗时任务，因此下沉到独立进程异步执行，对话轮内只做「提交任务」与「轮询状态」，不会阻塞 AiPy 对话。

## 工具清单

| 工具 | 作用 |
|------|------|
| `read_document` | 读取 Word / Markdown / 纯文本 / PDF，输出结构化正文 |
| `plan_video` | 依据正文生成分镜脚本（旁白 + 画面） |
| `inspect_script` | 校验脚本：时长估算、旁白长度、画面元素完整性 |
| `submit_render` | 提交渲染任务，立即返回任务 ID |
| `render_status` | 查询任务进度，完成后返回视频路径 |

## 运行前置：ffmpeg

**本插件不内置 ffmpeg**，需用户自行安装：

- macOS：`brew install ffmpeg`
- Windows：`winget install Gyan.FFmpeg`

插件会在系统 PATH 与常见安装路径（`/opt/homebrew/bin`、`C:\Program Files\ffmpeg\bin`、
winget / scoop / chocolatey 落地位置等）中自动查找；已安装但仍提示未找到时，
可用环境变量 `FFMPEG_PATH` 指定绝对路径。解析逻辑见 `server/lib/binaries.js`。

不内置的原因见 [vendor/README.md](vendor/README.md)：三平台全量约 126 MB，
打包后超过 GitHub Release 单文件 100 MB 硬限制。

## 本地开发

```bash
bun install
bun run build     # 生成 server.js
bun run dev       # 启动服务，输出 {"type":"http_start","port":N}
```

如果你本机没有装 ffmpeg，也可以拉到 `vendor/` 里做内置链路调试：

```bash
bash ../../scripts/fetch-ffmpeg.sh          # 自动识别当前平台
bash ../../scripts/fetch-ffmpeg.sh all      # 三平台全量（约 126 MB）
```

## 打包

```bash
bun run pack      # 等价于 npx @anthropic-ai/mcpb@2.1.2 pack . doc-video.mcpb
```

产物约 2 MB（`.mcpbignore` 已排除 `vendor/`）。若在本地临时移除 `/vendor/` 那行，
打包会带上二进制，仅建议用于离线验证，不要用于发布。

## 目录说明

```
agents/doc-video/
├── server/
│   ├── index.js              # MCP 服务入口，注册 5 个工具
│   ├── lib/
│   │   ├── binaries.js       # ffmpeg 路径解析（环境变量 → PATH → 常见安装路径）
│   │   ├── render-server.js  # 独立渲染服务端（异步执行）
│   │   └── renderer.js       # 渲染实现
│   └── tools/                # 各工具的业务逻辑
├── prompts/                  # 注入 AiPy 的系统提示词与补充指令
├── vendor/                   # 可选的本地内置 ffmpeg 目录（不随包分发，见 vendor/README.md）
├── manifest.json             # 扩展元信息与 user_config 定义
├── package.json
├── .mcpbignore               # 打包排除规则
├── protocol-check.mjs        # 协议层自检
├── smoke-test.mjs            # 冒烟测试
└── sample-doc.md             # 调试用样例文档
```

## 已知限制

- TTS 优先使用 Azure Speech，未配置时降级到 Edge TTS（音色选择范围更小）
- 渲染耗时与文案长度正相关，长文档请留意 `render_status` 的进度
- 渲染依赖系统 ffmpeg：未安装时 `submit_render` 会直接给出安装指引，不会静默失败
- Windows 侧解压 `~/.aipy/bin` 的缓存逻辑仍保留，供本地内置调试使用

## 参考

- [AiPy 智能体开发规范 V3.0](../../reference/AiPy智能体开发规范-V3.0.md)
- [仓库根 README](../../README.md)（发布流程与关键技术约定）
