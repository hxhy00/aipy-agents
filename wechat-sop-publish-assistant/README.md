# 公众号SOP发布助手（AiPy 智能体）

覆盖公众号文章「终稿 → 排版 → 草稿箱」链路的 AiPy 智能体扩展。

> **只写草稿箱，不做正式群发。** 最终发布由人工在公众平台确认。

## 目标链路

```
终稿（Word/md）→ read_draft 解析 → 排版 skill 选模板生成 HTML → publish_draft 导入后台草稿箱
```

## 功能

| 工具 | 说明 |
|------|------|
| `read_draft` | 解析终稿（`.docx` / `.md` / `.txt`）→ Markdown：识别标题层级、转换表格、抽取内嵌图片 |
| `publish_draft` | **微信渲染兼容性硬校验** → 正文图片中转上传（`uploadimg`）→ 封面永久素材（`add_material`）→ 写入草稿（`draft/add`） |
| `check_text` | 文字层校验：标点规范（半角/直引号）、品牌名（AiPY 大小写）、敏感词 |
| `check_wechat_compat` | 微信渲染兼容性自检：检出 `<style>`/`class`/`<script>`/伪元素/`position:fixed`/CSS 变量等会被微信剥离的写法 |
| `wordlist_stats` | 查看当前敏感词库装载情况（词条数量与类别），用于自检 |

## 为什么发布前要强制做渲染兼容性校验

微信草稿 API 在写入时会**静默重写** HTML：剥离 `<style>` 标签、剥离 `class` 属性、过滤 `<script>`/`<link>`/`<iframe>`，且**不报错、不提示**。

历史事故：排版时为了压缩体积把样式写进了 `<style>`，本地预检通过（预检只看体积、图片、转义），API 也返回成功，但用户打开草稿箱看到的是一篇**没有任何格式的纯文字**。

因此本智能体把兼容性校验放在**服务端**（`src/wechat_compat.py`），`publish_draft` 在写入草稿前强制执行：

- HTML 只要依赖 `<style>` / `class` / 伪元素 / `position:fixed` / CSS 变量 / `@font-face` 承载样式，**直接拒绝发布**并返回修复说明。
- 校验先于图片上传执行，避免白白消耗上传配额。
- 该保护不可绕过——「发布成功」必须等价于「用户看到的是对的」。

## 发布前推荐的自检顺序

```bash
# 1. 体积/图片/字段（skill 包内脚本）
python scripts/verify_html.py 排版.html --title "标题"
# 2. 微信渲染兼容性（最关键）
python scripts/verify_wechat_compat.py 排版.html
# 3. 内容保真反向核验
python scripts/verify_fidelity.py 终稿.md 排版.html --main-title "主标题"
# 4. 超限时无损压缩
python scripts/minify_inline_html.py 排版.html -o 排版.min.html
```

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

- AiPy 企业版 **Python 工具型**智能体（DXT / mcpb 规范）
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

## 发布链路与 skill 的分工

排版能力来自独立 skill 包 **`公众号文章SOP.zip`**（需单独安装到 AiPy）：

| 交付物 | 形式 | 作用 |
|--------|------|------|
| `wechat-sop-publish-assistant.dxt` | 智能体包 | 工具层：解析终稿、写草稿箱（含兼容性硬校验）、文字校验、兼容性自检 |
| `公众号文章SOP.zip` | skill 包 | 知识层：排版规范、风格矩阵、视觉素材库、三个预检脚本 + 无损压缩脚本 |

`read_draft` 产出的 Markdown 交给 skill 生成 HTML，再由 `publish_draft` 写入草稿箱。

## 打包上架

```bash
npx @anthropic-ai/dxt pack
# 产物 wechat-sop-publish-assistant.dxt，上传 AiPy 管理平台集市
```

## 已知限制

- 正文 ≤ 2 万字符且 < 1MB（微信硬限制，超限直接报错）
- 标题 ≤ 32 字、作者 ≤ 16 字、摘要 ≤ 120 字
- 外部图片 URL 会被微信过滤，代码强制要求本地图片并自动中转
- `.doc` 旧格式不支持，需另存为 `.docx`
- 视觉层问题（封面裁切、图片溢出、空行错乱）**无法自动检查**，需人工手机端预览确认
- 兼容性校验基于已知的微信剥离行为清单；微信平台策略调整后需同步更新 `src/wechat_compat.py`

