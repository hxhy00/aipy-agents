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

## 本地开发

```bash
bun install

# 只获取当前平台的 ffmpeg（约 90 MB）
bash ../../scripts/fetch-ffmpeg.sh

bun run build     # 生成 server.js
bun run dev       # 启动服务，输出 {"type":"http_start","port":N}
```

发版打包前需要三平台全量二进制（约 294 MB）：

```bash
bash ../../scripts/fetch-ffmpeg.sh all
```

## 打包

```bash
bun run pack      # 等价于 npx @anthropic-ai/mcpb@2.1.2 pack . doc-video.mcpb
```

产物约 140 MB，因为内置了三平台 ffmpeg，用户无需自行安装。

## 为什么 ffmpeg 二进制不入库

三平台全量约 294 MB，其中 `darwin-x64/ffmpeg` 单文件已逼近 GitHub 的 100 MB 硬限制。因此：

- **版本库只存代码**，`vendor/` 下仅保留目录结构与说明文件
- **本地与 CI 都通过 `scripts/fetch-ffmpeg.sh` 获取二进制**
- CI 在打 tag 时下载全量二进制再打包

`vendor/` **必须随包分发**，不要加进 `.mcpbignore`。

## 目录说明

```
agents/doc-video/
├── server/
│   ├── index.js              # MCP 服务入口，注册 5 个工具
│   ├── lib/
│   │   ├── binaries.js       # ffmpeg 路径解析（三平台）+ Windows 侧惰性解压
│   │   ├── render-server.js  # 独立渲染服务端（异步执行）
│   │   └── renderer.js       # 渲染实现
│   └── tools/                # 各工具的业务逻辑
├── prompts/                  # 注入 AiPy 的系统提示词与补充指令
├── vendor/                   # ffmpeg 二进制归位目录（见 vendor/README.md）
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
- Windows 侧 ffmpeg 以 `.gz` 存放，首次调用时解压到 `~/.aipy/bin`，多等几秒属正常

## 参考

- [AiPy 智能体开发规范 V3.0](../../reference/AiPy智能体开发规范-V3.0.md)
- [仓库根 README](../../README.md)（发布流程与关键技术约定）
