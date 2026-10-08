# 公众号SOP发布助手（AiPy 智能体）

覆盖公众号文章「终稿 → 排版 → 草稿箱」链路的 AiPy 智能体扩展。

> **只写草稿箱，不做正式群发。** 最终发布由人工在公众平台确认。

## 目标链路

```
终稿（Word/md）→ read_draft 解析 → 读内置知识层（get_sop / get_reference / get_asset）→ 按规则排版生成 HTML → publish_draft 导入后台草稿箱
```

## 功能

共 **13 个 MCP 工具**：5 个基础工具 + 5 个确定性能力（原独立排版脚本改造为工具）+ 3 个知识层读取。

| 分组 | 工具 | 说明 |
|------|------|------|
| 基础 | `read_draft` | 解析终稿（`.docx` / `.md` / `.txt`）→ Markdown：识别标题层级、转换表格、抽取内嵌图片 |
| 基础 | `publish_draft` | **微信渲染兼容性硬校验** → 正文图片中转上传（`uploadimg`）→ 封面永久素材（`add_material`）→ 写入草稿（`draft/add`） |
| 基础 | `check_wechat_compat` | 微信渲染兼容性自检：检出 `<style>`/`class`/`<script>`/伪元素/`position:fixed`/CSS 变量等会被微信剥离的写法 |
| 基础 | `check_text` | 文字层校验：标点规范（半角/直引号）、品牌名（AiPY 大小写）、敏感词 |
| 基础 | `wordlist_stats` | 查看当前敏感词库装载情况（词条数量与类别），用于自检 |
| 能力 | `extract_template_style` | 用户给了参考模板/案例目录时，从模板抽取结构化设计参数（配色、字号、圆角、标题骨架等）供原创化融合 |
| 能力 | `verify_html` | 发布可行性预检（体积/图片/字段）：检出 base64 内嵌图、外链图、缺失图片、未解码转义、正文/标题/摘要/作者超限 |
| 能力 | `verify_fidelity` | 内容保真反向核验：逐段比对源终稿与排版 HTML，检出缺失/多出/错序段落与数字不一致 |
| 能力 | `minify_inline_html` | 内联样式 HTML 无损压缩，解决微信正文 2 万字符 / 1MB 硬限制（不改正文、不引入 `<style>`/`class`） |
| 能力 | `render_code_images` | 把 Markdown 围栏代码块渲染成微信安全的 PNG（可选配色、字号、行号、按列折行） |
| 知识层 | `get_sop` | 读取内置排版全流程 SOP（`resources/SOP.md`），可按章节取；**任何排版任务开始前先调一次** |
| 知识层 | `get_reference` | 按文件名读取单篇排版规范（`style_matrix`、`wechat_layout_rules`、`content_fidelity_rules` 等） |
| 知识层 | `get_asset` | 读取视觉素材库里的可复用片段源码（`style_examples` / `color_palettes` / `icons` / `dividers` / `card_patterns`） |

> 这些工具都由智能体直接注册，**用工具调用，不要用 shell 去跑文件**。排版规范与素材已随包打进 `resources/`，由上面 3 个知识层工具读取，不需要额外安装任何其他包。

## 为什么发布前要强制做渲染兼容性校验

微信草稿 API 在写入时会**静默重写** HTML：剥离 `<style>` 标签、剥离 `class` 属性、过滤 `<script>`/`<link>`/`<iframe>`，且**不报错、不提示**。

历史事故：排版时为了压缩体积把样式写进了 `<style>`，本地预检通过（预检只看体积、图片、转义），API 也返回成功，但用户打开草稿箱看到的是一篇**没有任何格式的纯文字**。

因此本智能体把兼容性校验放在**服务端**（`src/wechat_compat.py`），`publish_draft` 在写入草稿前强制执行：

- HTML 只要依赖 `<style>` / `class` / 伪元素 / `position:fixed` / CSS 变量 / `@font-face` 承载样式，**直接拒绝发布**并返回修复说明。
- 校验先于图片上传执行，避免白白消耗上传配额。
- 该保护不可绕过——「发布成功」必须等价于「用户看到的是对的」。

## 发布前推荐的自检顺序

以下都是**智能体直接调用的 MCP 工具**，不是命令行脚本：按顺序调工具即可。

```text
# 0. 文章里有代码块时，先渲染成 PNG 再当本地图片引用
render_code_images(md_path="终稿.md", out_dir="images")
# 1. 体积/图片/字段
verify_html(html_path="排版.html", title="标题")
# 2. 微信渲染兼容性（最关键）
check_wechat_compat(html_path="排版.html")
# 3. 内容保真反向核验
verify_fidelity(source="终稿.md", html="排版.html", main_title="主标题")
# 4. 仅当第 1 步报「正文超限」时才做无损压缩
minify_inline_html(html_path="排版.html", out_path="排版.min.html")
# 以上三关都通过后，才允许写草稿箱
publish_draft(html_path="排版.html", title="标题", cover_path="封面.png")
```

压缩后必须重跑第 2、3 步：确认没有引入 `<style>`/`class`，且内容仍然 100% 保真。

## read_draft 解析规则

- Word 的「标题 1 / Heading 1」→ `#`，「标题 2」→ `##`，以此类推（最多 6 级）
- Word 表格 → Markdown 表格
- 内嵌图片抽取到终稿同目录 `images/`，正文文末以 `![](images/文件名)` 引用（插入位置与图注需人工确认）
- `.md` / `.txt` 直接读取并规整空行
- 未识别到标题样式时给出提示（此时章节导航会缺失）

## 敏感词引擎

- **算法**：`pyahocorasick`（Aho-Corasick 多模式匹配，C 扩展加速，返回命中位置）
- **词库**：内置 4 类高风险词表（广告法极限词 / 医疗功效 / 金融承诺 / 违禁导流），共 56 词
- **扩展**：设置 `SENSITIVE_WORDLIST` 环境变量指向 txt（一行一词），与内置词表合并

> 为什么不用现成 Python 敏感词包：`sensitive-word`(PyPI 0.5) 实为 `textfilter`，仅能打码不返回命中位置；
> `sensitive-words` 在 PyPI 上不存在；`flashtext` 已停止维护。故采用「成熟算法库 + 自带词库」组合。

## 技术形态

- AiPy 企业版 **Python 工具型**智能体（DXT 规范）
- Streamable HTTP Server（`mcp 1.x` + Starlette + uvicorn，动态端口）
- Python 3.12，依赖用 **uv** 管理
- AppID / AppSecret 通过 `user_config` 注入环境变量

## 使用前置条件

1. 公众号已完成**微信认证**
2. 在公众平台「设置与开发 → 基本配置」拿到 AppID / AppSecret
3. 将**本机出口公网 IP** 加入后台 **IP 白名单**（否则报 `errcode 40164`）

> 开发环境需设置镜像源：`export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple`

## 本地运行

```bash
uv sync
uv run main.py
# 标准输出：{"type": "http_start", "port": 60155}
```

## 交付物与内部分层

自 2.0.0 起**只有一个交付物**：`wechat-sop-publish-assistant.dxt`。排版知识库已合并进本智能体（随包打进 `resources/`），不再有需要单独安装的独立包。

单包内部按职责分三层：

| 层 | 内容 | 对应工具 |
|----|------|----------|
| 解析层 | 终稿（Word/md/txt）→ Markdown | `read_draft` |
| 知识层 | 随包 `resources/`：SOP 全流程规则、排版规范、视觉素材库 | `get_sop` / `get_reference` / `get_asset` |
| 工具层 | 模板抽取、发布预检、保真核验、无损压缩、代码块出图 | `extract_template_style` / `verify_html` / `verify_fidelity` / `minify_inline_html` / `render_code_images` |
| 发布层 | 文字与兼容性校验 → 写草稿箱（含兼容性硬校验） | `check_text` / `check_wechat_compat` / `wordlist_stats` / `publish_draft` |

链路：`read_draft` 产出 Markdown → 模型按 `get_sop` / `get_reference` / `get_asset` 给出的规则与素材生成 HTML → 预检三关通过后由 `publish_draft` 写入草稿箱。

> 排版规则与素材不再由 shell 读文件：模型一律通过 `get_sop` / `get_reference` / `get_asset` 读取，这三个工具带白名单校验，也保证换机器安装后照样可用。

## 打包上架

推荐用仓库的自动化流程：打 tag 推送到 GitHub，CI 会自动构建产物并挂到 Release。

本地手动打包：

```bash
npx @anthropic-ai/mcpb@2.1.2 pack . wechat-sop-publish-assistant.dxt
# 产物 wechat-sop-publish-assistant.dxt，上传 AiPy 管理平台集市
```

> 打包器说明：`@anthropic-ai/dxt` 已被官方废弃并更名为 `@anthropic-ai/mcpb`，
> 但**改名的是打包 CLI，不是产物**：AiPy Pro 2.1.0 安装扩展的后缀白名单只有 `zip` / `dxt`，
> `.mcpb` 会被客户端直接拒绝。所以沿用 `mcpb` CLI 打包，显式指定 `.dxt` 输出名。
> 安装方式不变（AiPy 客户端本地安装）。背景见[仓库根 README](../../README.md)（打包器）。

## 已知限制

- 正文 ≤ 2 万字符且 < 1MB（微信硬限制，超限直接报错）
- 标题 ≤ 32 字、作者 ≤ 16 字、摘要 ≤ 120 字
- 外部图片 URL 会被微信过滤，代码强制要求本地图片并自动中转
- `.doc` 旧格式不支持，需另存为 `.docx`
- 视觉层问题（封面裁切、图片溢出、空行错乱）**无法自动检查**，需人工手机端预览确认
- 兼容性校验基于已知的微信剥离行为清单；微信平台策略调整后需同步更新 `src/wechat_compat.py`

