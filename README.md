# AiPy 智能体扩展集

面向 [AiPy](https://www.aipy.app) 客户端的智能体扩展（MCP Bundle）开发仓库。`agents/` 下每个子目录即一个自研智能体，独立打包、独立发版；并归档官方开发规范与示例代码。

## 仓库结构

```
.
├── .github/workflows/
│   ├── check.yml                 # 日常校验：语法、凭据泄露、目录约定
│   └── release.yml               # 打 tag 时构建产物并发布 Release
├── agents/                       # 自研智能体
│   └── wechat-publish/           # 公众号发布套件（Python，单智能体）
│       ├── main.py               #   扩展入口：MCP 服务，13 个工具
│       ├── src/                  #   解析 / 校验 / 发布逻辑，工具实现
│       └── resources/            #   内置知识层：SOP + 排版规范 + 视觉素材，随包分发
├── docs/                         # 项目文档
│   └── 实现规划.md               #   公众号发布套件实现规划
└── reference/                    # 参考资料，不参与构建
    ├── AiPy智能体开发规范-V3.0.md
    ├── examples-enterprise/      #   官方示例（企业版）
    ├── examples-cybersecurity/   #   官方示例（网安版）
    ├── cases-enterprise/         #   官方实际案例（企业版）
    └── cases-cybersecurity/      #   官方实际案例（网安版）
```

## 自研智能体

每个扩展打一个包，装一个包就能用。

| 项目 | 类型 | 技术栈 | 产物 | 体积 |
|------|------|--------|------|------|
| `agents/wechat-publish` | 工具型（conversation-tool） | Python 3.12 + uv + MCP + Pygments + Pillow | `wechat-sop-publish-assistant.dxt` | 约 197 KB |

> 公众号发布套件 2.0.1 起不再有独立的排版 skill 包：排版知识与预检能力已并入上面这一个 `.dxt`，用户只装一个包。

> **请使用 2.0.2 或更高版本**：`wechat-v2.0.0` 的 Release 附件后缀为 `.mcpb`，AiPy 无法安装；首个可用版本是 2.0.1（产物后缀已修正为 `.dxt`）。

## 本地开发

### 公众号发布套件

```bash
cd agents/wechat-publish
uv sync
uv run main.py
# 标准输出：{"type": "http_start", "port": 60155}
```

排版知识库在 `resources/`，随包走，本地无需额外准备。13 个工具全部由本智能体提供，模型直接调用，不需要在终端跑任何脚本。

`render_code_images`（代码块转图片）需要系统里有一款**带中文字形**的字体，macOS / Windows / 主流 Linux 发行版默认都有；若提示找不到字体，装一份思源黑体（Source Han Sans）即可。详见下文「代码块转图片为什么不用 Playwright」。

## 发布流程

### 关于 CI / CD 的定位

打包流程严格来说属于 **CI 的一部分，同时承担了 CD 的交付动作**：

| 阶段 | 归属 | 本仓库的对应 |
|------|------|--------------|
| 代码提交后校验（语法、凭据泄露、目录约定） | **CI**（持续集成） | `check.yml`，push / PR 触发 |
| 构建产物（打包 `.dxt`） | **CI**（构建属于集成的延伸） | `release.yml` 的 `wechat-publish` job |
| 发布产物到 Release（交付给用户） | **CD**（持续交付） | `release.yml` 的 `publish` job |

业界把「构建 + 产出可交付物」通常统称 CI，「把产物送到用户手里」才叫 CD。本仓库两者放在同一个 workflow，通过 job 依赖串起来。注意这里只做到**交付**（Release 附件待人工确认），没有做到**部署**（自动上架到 AiPy 集市），所以严格说是 CD 中的「持续交付」而非「持续部署」。

### 发版步骤

发版用**带扩展前缀的 tag** 触发，CI 靠前缀判断这次该构建哪个扩展。当前只有一个扩展，但前缀机制保留，后续新增扩展直接沿用：

| 扩展 | tag 形式 | 触发 job | 产物 |
|------|----------|----------|------|
| 公众号发布套件 | `wechat-v2.0.2` | `wechat-publish` | `wechat-sop-publish-assistant.dxt` |

```bash
# 1. 改版本号（tag 去掉对应前缀后必须等于 manifest 里的 version，CI 会校验）
#    公众号发布套件：agents/wechat-publish/manifest.json 的 version
#                    （同时需与同目录 pyproject.toml 的 version 一致）

# 2. 打 tag 并推送
git tag wechat-v2.0.2
git push origin wechat-v2.0.2
```

推送 tag 后 CI 自动完成：

1. 校验 tag 版本与 `manifest.json` 版本一致（不一致直接失败；同时校验 `pyproject.toml`）
2. 打包智能体（知识库随包走，不单独产出 zip）
3. 校验产物内容（必需文件是否齐全、虚拟环境 / 源码是否误入包、失效引用是否写回文档、体积是否异常）
4. 创建 GitHub Release 并上传本次构建的产物

也可以到 Actions 页面手动触发 `workflow_dispatch`（此时会直接打包，版本一致性校验自动跳过）。

### 为什么日常 push 不打包

打包是发版动作，产物只在打 tag 时才需要，而日常改动大多只是改一行文案或路径。因此拆成两个 workflow：日常只跑秒级的轻量校验（语法、凭据、结构约定），打 tag 才构建与发布。

## 关键技术约定

### 打包器

构建用 `@anthropic-ai/mcpb@2.1.2`，但**产物后缀是 `.dxt`**。这两件事在上游公告里是连在一起说的，落到 AiPy 上却必须拆开，否则产物直接装不上：

| 层面 | 事实 |
|------|------|
| 上游工具 | Anthropic 把打包 CLI 从 `@anthropic-ai/dxt` 改名为 `@anthropic-ai/mcpb`，产物默认后缀随之变成 `.mcpb` |
| 目标平台 | AiPy 客户端**没有跟进这次改名**。AiPy Pro 2.1.0 的 `app.asar` 里，装扩展的后缀白名单写死为 `[".zip", ".dxt"]`，文件选择器只放行 `zip / dxt / md`，整个应用包内 `.mcpb` 出现 0 次；AiPy 商店所有扩展的下载链接也全部以 `.dxt` 结尾 |

**打包工具叫什么，和产物能不能被平台装上，是两件事。** 平台认的是文件后缀白名单，不认 CLI 包名；本仓库的约定因此是「用 `mcpb` CLI 打包，**显式指定 `.dxt` 输出名**」——`release.yml` 里的打包命令直接写死 `pack . wechat-sop-publish-assistant.dxt`，产物名是构造上确定的，不另加后缀校验。

这条约束靠「命令写对」保证，不靠运行时拦截兜底：`pack <目录>` 省略输出参数时才会回落到打包器默认后缀 `.mcpb`（见下方实测差异），而仓库里从 CI 到本地脚本一律显式传了输出名，真要防回归只需保证命令不被改回省略形式。

> 顺带说明改名为什么是安全的：`.dxt` 与 `.mcpb` 都是 zip 容器，改名后包内 `manifest.json` 哈希完全一致、内容零差异，且包内已有 AiPy 读取的 `"dxt_version": "0.1"`。所以改的只是文件名，不是包内容。

**踩坑教训**：这类「上游弃用 / 上游改名」的结论，必须**以目标平台的后缀白名单实测为准**，不能直接套用上游公告。本次就是直接套用公告、把产物写成 `.mcpb`，结果 AiPy 装不上。对照物一直摆在官方规范里——规范至今仍写「选择 .dxt 文件导入」、示例产物是 `python.dxt`，那才是 AiPy 实际支持形态的准确描述。

两个实测确认的行为差异：

- `pack <目录>` 省略输出参数时，产物文件名取自**目录名**、后缀沿用打包器默认值（在 `agents/wechat-publish/` 下会得到 `wechat-publish.mcpb`）。目录名与目标产物名不一致，默认后缀平台又不认，因此脚本与 CI 一律显式指定输出文件名，产物固定为 `wechat-sop-publish-assistant.dxt`。
- 打包器硬校验 `manifest.icon` 指向的文件必须是 **PNG**（读文件头魔数），SVG 会直接导致打包失败。本仓库保留 SVG 作为设计源文件，另生成 `icon.png` 供打包使用，转换命令：

```bash
sips -s format png -Z 512 icon.svg --out icon.png
```

`check.yml` 会提前拦截非 PNG 的图标引用。

### 打包忽略文件

构建期的规则文件叫 `.mcpbignore`，产物后缀叫 `.dxt`。两个名字长得像，用途完全不同：

| | `.mcpbignore` | `.dxt` |
|---|-------------|------|
| 是什么 | 打包时读取排除规则的**文件** | 打包产物的**文件名后缀** |
| 谁在用 | `mcpb pack`，构建时读 | AiPy 客户端安装时按后缀白名单判断 |
| 写错的后果 | 规则失效，`.venv` / `node_modules` 被整包打进产物 | 用户在客户端里选不中、装不上 |

`.dxtignore` 是旧版打包器的规则文件名，混用会让排除规则整体失效。`check.yml` 里那条针对 `.dxtignore` 的检查是**有意保留**的：拦住有人误建或误用 `.dxtignore`，把 `.venv` 之类本该排除的目录打进包（该检查为警告级、不阻断流水线，但足以在 PR 里点出来）。

公众号发布套件的忽略规则里有两条容易踩的：

- `resources/` 下的 `.md` **必须保留**——那是模型直接读取的知识层，排除掉等于智能体没了排版能力。排除的是根级 `README.md`（开发说明，给维护者看的，不随包分发）。
- **`uv.lock` 必须保留进包**——本扩展不是构建产物而是源码直跑，宿主以 `uv run` 启动（见 `manifest.json`），锁文件是用户机器上依赖解析可复现的唯一依据。排除它等于把版本漂移留给终端用户；「它不是源码所以不该进包」是误判。
- 当前产物 52 个文件、约 197 KB，其中 `resources/` 占 31 个（`uv.lock` 随包后新增 1 个文件、约 224 KB 未压缩）。体积上限校验在 `release.yml`，知识库变大时会先被拦下。

### 为什么排版 skill 被合并进智能体

2.0.1 之前，公众号发布套件发两个 AiPy 扩展：一个智能体（`.dxt`）+ 一个 skill（`.zip`，需单独安装）。现在合并为一个智能体。合并的理由不是「少发一个文件」，而是 AiPy 规范里 **skill 与智能体是两种并列的项目类型**：

| | skill | 智能体 |
|---|------|--------|
| 模型怎么发现它 | 靠 `SKILL.md` 的 description 关键词被唤起 | 只把 MCP 工具暴露给模型 |
| 脚本怎么执行 | 模型自己在终端敲命令 | 模型调用工具，由服务端执行 |

把 skill 目录原样塞进 `.dxt`，文件虽然在包里，但模型完全感知不到，`$skill名` 引用会失效——那是**静默丢功能**，不是合并。真正的合并是把 skill 的能力翻译成两层：

- **知识层**：排版 SOP、10 篇排版规范、19 个视觉素材搬进 `resources/`，由 `get_sop` / `get_reference` / `get_asset` 三个工具按白名单读取（只允许按文件名取，不接受任意路径）。
- **工具层**：原来的 7 个脚本拆成两类——5 个变成独立工具（`extract_template_style`、`verify_html`、`verify_fidelity`、`minify_inline_html`、`render_code_images`），另 2 个与工具层已有实现合并（`read_draft`、`check_wechat_compat`，见下文「两处重复实现的合并」）。

加上原有的 5 个工具，共 13 个。

破坏性变更：安装方式从「装两个包」变成「装一个包」，原独立的排版 skill zip 不再发布。

### 代码块转图片为什么不用 Playwright

原方案用 Playwright + Chromium 渲染代码块截图（约 150 MB），**装不进 `.dxt`**。保留它等于用户装完包还要额外装浏览器，抵消了合并收益。改用 Pygments 自带的 `ImageFormatter` + Pillow，纯 Python 出图，实测中文注释能正常成像。

代价是要自己解决字体：Menlo、Consolas、DejaVu Sans Mono、Courier New 这些常见等宽字体都没有中文字形，直接用会把中文注释渲染成空白——读者看到的是「注释消失了」。实现按平台解析中文字体路径的候选链（macOS 苹方/宋体、Windows 微软雅黑、Linux 思源黑体/文泉驿），逐个用 Pillow 实际加载探测（只看文件存在会踩 Pillow 对部分字体集合支持有限的坑），macOS 实测命中 `Songti.ttc`。

一个候选都探不到时不静默出图：退回纯 ASCII 等宽字体并在结果里明确告知「中文注释会显示为空白」，同时建议安装思源黑体 / Noto Sans CJK。

依赖因此新增 `pygments>=2.17.0,<3` 与 `Pillow>=10.3.0,<13`；原先 `python-docx` 是运行时现场安装，现已改为正式依赖。缺任一依赖时只影响对应工具，其余照常可用。

### 两处重复实现的合并

合并前有两组「同一个功能两份实现」：

| 功能 | 原来的两份 | 统一后 |
|------|-----------|--------|
| 读终稿 | skill 的 `read_draft.py` 与 `src/parser.py`（重复约 80%） | `src/parser.py` |
| 微信兼容性校验 | `verify_wechat_compat.py` 与 `src/wechat_compat.py` | `src/wechat_compat.py`，规则集取 skill 侧更全的那份 |

规则集取全的那份带来两处加强：禁用标签 9 个 → 10 个（补 `audio`），违规定位带上行号；另新增 5 类检查（`nowrap` 无配套 `overflow`、`<pre>` 文本代码块、`word-break:break-all`、重复内联样式、overflow 横向滚动），阻断类 error 从 7 类增至 12 类。

### 防回归守卫

合并最大的失败模式是「文档里写回已删除的路径，然后模型去执行不存在的脚本」。`check.yml` 加了 grep 守卫拦住它：

- `resources/` 与 `manifest.json` 是模型直接读取的内容，禁止重新出现已删除的 skill 目录名，或已合并的排版 skill 曾有的脚本路径（如 `scripts/read_draft.py`，原在 `skills/wechat-article-sop-layout/scripts/` 下）——这些脚本已随 skill 合并改造成 MCP 工具并删除，写回文档等于让模型去执行不存在的文件。仓库根的 `scripts/` 目录同样不存在，别当成可用目录（`resources/evals/` 是评测基线，允许记录历史脚本名，例外）。
- `src/` 与 `pyproject.toml` 里禁止重新引入 `playwright`。

这两条与上面的删除动作同等重要，删了路径不等于删了引用。

### 凭据管理

所有第三方凭据（当前仅微信公众号 AppSecret）一律通过 AiPy 的 `user_config` 注入，Python 扩展中用 `os.environ.get()` 读取，**禁止硬编码静默回退**。`check.yml` 会扫描源码拦截硬编码凭据。

### 微信渲染兼容性

微信公众号草稿 API 会**静默剥离** `<style>` 标签与 `class` 属性（不报错、不提示），导致草稿箱里只剩纯文字。因此所有样式必须内联为 `style` 属性。该约束由智能体在两处强制拦截：`publish_draft` 的服务端硬校验（`src/wechat_compat.py`），以及发布前可主动调用的自检工具 `check_wechat_compat`。合并后二者共用同一份规则集，不再各维护一套。

## 参考文档

- [AiPy 智能体开发规范 V3.0](reference/AiPy智能体开发规范-V3.0.md)
- [公众号发布套件实现规划](docs/实现规划.md)

## 注意

`reference/` 目录为官方资料归档，其中的示例代码沿用了废弃的 `@anthropic-ai/dxt` 与旧目录约定，**仅作参考，不要照抄**。请以 `agents/` 下的实现为准。

需要区分的是：规范里的 **`.dxt` 产物与 `.dxt` 安装流程是 AiPy 真实支持的形态**（照抄没错），需要跟上游一起更新的只有打包 CLI 与它的排除规则文件名（`@anthropic-ai/dxt` → `@anthropic-ai/mcpb`、`.dxtignore` → `.mcpbignore`，见「打包器」与「打包忽略文件」）。
