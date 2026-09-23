# AiPy 智能体扩展集

面向 [AiPy](https://www.aipy.app) 客户端的智能体扩展（MCP Bundle）开发仓库。以 monorepo 形式管理自研智能体，并归档官方开发规范与示例代码。

## 仓库结构

```
.
├── .github/workflows/
│   ├── check.yml                 # 日常校验：语法、凭据泄露、目录约定
│   └── release.yml               # 打 tag 时构建产物并发布 Release
├── agents/                       # 自研智能体
│   ├── wechat-publish/           # 公众号发布套件
│   │   ├── publisher/            #   智能体：解析终稿 → 写草稿箱（Python）
│   │   ├── skills/
│   │   │   └── wechat-article-sop-layout/   #   skill 包：排版 SOP
│   │   ├── docs/                 #   需求与实现规划
│   │   └── 需求/                 #   业务原始文档（本地保留，不入库）
│   └── doc-video/                # 文档一键成片（Node.js）
│       ├── server/               #   服务端源码
│       ├── prompts/              #   注入 AiPy 的系统提示词
│       └── vendor/               #   ffmpeg 二进制目录（二进制不入库）
├── scripts/
│   └── fetch-ffmpeg.sh           # 三平台 ffmpeg 获取脚本（本地与 CI 复用）
└── reference/                    # 参考资料，不参与构建
    ├── AiPy智能体开发规范-V3.0.md
    ├── examples-enterprise/      #   官方示例（企业版）
    ├── examples-cybersecurity/   #   官方示例（网安版）
    ├── cases-enterprise/         #   官方实际案例（企业版）
    └── cases-cybersecurity/      #   官方实际案例（网安版）
```

## 两个自研智能体

| 项目 | 类型 | 技术栈 | 产物 | 体积 |
|------|------|--------|------|------|
| `agents/wechat-publish` | 工具型（conversation-tool） | Python 3.12 + uv + MCP | `wechat-sop-publish-assistant.mcpb` | 约 60 KB |
| `agents/wechat-publish` | skill 包 | Markdown + Python 脚本 | `wechat-article-sop-layout.zip` | 约 200 KB |
| `agents/doc-video` | 工具型（conversation-tool） | Node.js 22 + Bun + MCP | `doc-video.mcpb` | 约 140 MB |

`doc-video` 体积大是因为内置了三平台 ffmpeg 二进制，用户无需自行安装 ffmpeg。

## 本地开发

### 公众号发布套件

```bash
cd agents/wechat-publish/publisher
uv sync
uv run main.py
# 标准输出：{"type": "http_start", "port": 60155}
```

### 文档一键成片

```bash
cd agents/doc-video
bun install
bash ../../scripts/fetch-ffmpeg.sh        # 只取当前平台，约 90 MB
bun run build                             # 生成 server.js
bun run dev
```

需要三平台全量二进制（约 294 MB，发版打包前用）：

```bash
bash scripts/fetch-ffmpeg.sh all
```

## 发布流程

### 关于 CI / CD 的定位

打包流程严格来说属于 **CI 的一部分，同时承担了 CD 的交付动作**：

| 阶段 | 归属 | 本仓库的对应 |
|------|------|--------------|
| 代码提交后校验（语法、凭据泄露、目录约定） | **CI**（持续集成） | `check.yml`，push / PR 触发 |
| 构建产物（打包 .mcpb） | **CI**（构建属于集成的延伸） | `release.yml` 的 `wechat-publish` / `doc-video` 两个 job |
| 发布产物到 Release（交付给用户） | **CD**（持续交付） | `release.yml` 的 `publish` job |

业界把「构建 + 产出可交付物」通常统称 CI，「把产物送到用户手里」才叫 CD。本仓库两者放在同一个 workflow，通过 job 依赖串起来。注意这里只做到**交付**（Release 附件待人工确认），没有做到**部署**（自动上架到 AiPy 集市），所以严格说是 CD 中的「持续交付」而非「持续部署」。

### 发版步骤

```bash
# 1. 改版本号（两处必须一致，CI 会校验）
#    agents/wechat-publish/publisher/manifest.json  的 version
#    agents/doc-video/manifest.json                 的 version

# 2. 打 tag 并推送（tag 去掉 v 前缀后必须等于 manifest 里的 version）
git tag v1.1.0
git push origin v1.1.0
```

推送 tag 后 CI 自动完成：

1. 校验 tag 版本与 `manifest.json` 版本一致（不一致直接失败）
2. `doc-video`：安装依赖 → 获取三平台 ffmpeg → `bun run build` → 补可执行位 → 打包
3. `wechat-publish`：打包智能体 + 压缩 skill 包
4. 校验产物内容（必需文件是否齐全、虚拟环境与源码是否误入包）
5. 创建 GitHub Release 并上传三个产物

也可以到 Actions 页面手动触发 `workflow_dispatch`。

### 为什么日常 push 不打包

`doc-video` 打包需要下载约 294 MB 的 ffmpeg 且 Bun 打包耗时较长，每次 push 都跑会浪费 CI 额度。因此拆成两个 workflow：日常只跑秒级的轻量校验，打 tag 才做重活。

## 关键技术约定

### 打包器

使用 `@anthropic-ai/mcpb@2.1.2`。原始包名 `@anthropic-ai/dxt` 已被官方废弃，产物扩展名从 `.dxt` 变为 `.mcpb`。

两个实测确认的行为差异：

- `pack <目录>` 省略输出参数时，产物文件名取自**目录名**而非扩展名（在 `publisher/` 下会得到 `publisher.mcpb`）。因此脚本与 CI 一律显式指定输出文件名。
- 打包器硬校验 `manifest.icon` 指向的文件必须是 **PNG**（读文件头魔数），SVG 会直接导致打包失败。本仓库保留 SVG 作为设计源文件，另生成 `icon.png` 供打包使用，转换命令：

```bash
sips -s format png -Z 512 icon.svg --out icon.png
```

`check.yml` 会提前拦截非 PNG 的图标引用。

### 打包忽略文件

统一使用 `.mcpbignore`（新版打包器的规则文件名）。若目录下同时存在 `.dxtignore`，新版可能不再识别，导致虚拟环境等文件被误打进包。

### 凭据管理

所有第三方凭据（微信公众号 AppSecret、Azure Speech Key、搜索 API Key）一律通过 AiPy 的 `user_config` 注入，代码中用 `os.environ.get()` / `process.env` 读取，**禁止硬编码静默回退**。`check.yml` 会扫描源码拦截硬编码凭据。

### 内置二进制与可执行位

`mcpb` 打包器在 Linux/macOS 上会正确写入 Unix 权限位，但在 Windows 上不写（上游已知问题）。因此 CI 固定在 `ubuntu-latest` 上打包，并在打包前显式 `chmod +x`，否则用户侧调用 ffmpeg 会报 `EACCES`。

### 微信渲染兼容性

微信公众号草稿 API 会**静默剥离** `<style>` 标签与 `class` 属性（不报错、不提示），导致草稿箱里只剩纯文字。因此所有样式必须内联为 `style` 属性。该约束在三处强制拦截：skill 的 `verify_wechat_compat.py`、智能体 `publish_draft` 服务端校验、独立的 `check_wechat_compat` 工具。

## 参考文档

- [AiPy 智能体开发规范 V3.0](reference/AiPy智能体开发规范-V3.0.md)
- [公众号发布套件实现规划](agents/wechat-publish/docs/实现规划.md)

## 注意

`reference/` 目录为官方资料归档，其中的示例代码沿用了废弃的 `@anthropic-ai/dxt` 与旧目录约定，**仅作参考，不要照抄**。请以 `agents/` 下的实现为准。
