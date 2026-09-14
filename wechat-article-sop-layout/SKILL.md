---
name: wechat-article-sop-layout
description: WeChat article SOP skill — layout design AND full-pipeline SOP for taking a Word/Markdown/TXT draft all the way to the WeChat Official Account draft box — parse manuscript, pick style, generate mobile-first WeChat HTML, pre-check, then publish via the wechat-sop-publish-assistant agent. Includes deterministic scripts (scripts/read_draft.py for docx/md/txt parsing, scripts/verify_html.py for volume/image/field validation, scripts/verify_wechat_compat.py to block <style>/class which WeChat strips and causes format loss in the draft box, scripts/verify_fidelity.py for 100% content-fidelity reverse checking, scripts/minify_inline_html.py for lossless inline-style compression, scripts/code_image.py for rendering fenced code blocks as WeChat-safe images — text code blocks always break in WeChat). Use for 公众号文章SOP、公众号排版、公众号美化、公众号视觉设计、生成公众号HTML、Word转公众号、企业宣传推文、活动推文、产品发布、公众号模板或风格学习, and for 终稿到草稿箱全流程、docx转公众号、文章解析与发布、从Word到公众号草稿箱. Preserve source wording, numbers, names, punctuation, paragraph order, heading structure, and embedded images; omit the document’s first-line main title from body HTML by default; generate a visual navigation block under each level-one body heading from its original level-two headings; dynamically combine rich titles, cards, borders, dividers, textures, highlights, image treatments, quotes, and other WeChat-safe visual elements instead of producing plain text or a fixed template. All styles MUST be inline style attributes — never <style> tags or class attributes.
---

# AI 公众号视觉设计师

像专业公众号视觉设计师一样分析、设计、排版和验收。视觉设计是核心目标；内容与图片保真是不可突破的底线。

## 全流程 SOP：终稿 → 草稿箱

当用户要求「从终稿一路做到公众号草稿箱」时，按下面 6 步执行。**每一步都标明了由谁做**：`[脚本]` = 运行确定性脚本，`[AI]` = 你（模型）来设计与判断，`[工具]` = 调用智能体（`wechat-sop-publish-assistant`）提供的 MCP 工具。

| 步骤 | 执行者 | 动作 | 产物 |
|------|--------|------|------|
| 1. 解析终稿 | `[脚本]` | `python scripts/read_draft.py <终稿路径>` | `.parsed.md` + 抽取的图片 |
| 2. 选模板 | `[AI]` | 读 `references/style_matrix.md`，按主题选风格 | 设计分析说明 |
| 3. 生成 HTML | `[AI]` | 按本文档「工作流程」设计排版（样式全部内联） | 公众号 HTML 文件 |
| 4. 预检 | `[脚本]` | 依次跑 `verify_html.py` → `verify_wechat_compat.py` → `verify_fidelity.py`；超限时跑 `minify_inline_html.py` | 通过/问题清单 |
| 5. 发布 | `[工具]` | 调智能体 `publish_draft`（服务端会再校验一次兼容性） | 草稿箱 media_id |

> **务必按顺序跑第 4 步的三个脚本。** 只跑 `verify_html.py` 是不够的：它检查的是「发布会不会失败」，而 `verify_wechat_compat.py` 检查的是「发布后用户看到的有没有格式」。历史事故就是只跑了前者、把样式写进 `<style>`/`class`，预检通过但草稿箱里是一篇纯文字。

### 步骤 1：解析终稿 `[脚本]`

```bash
python scripts/read_draft.py /path/to/终稿.docx
```

- 支持 `.docx` / `.md` / `.txt`。`.docx` 依赖 `python-docx`，缺失时先 `uv pip install python-docx`。
- 脚本输出 JSON：主标题 `title`、标题数 `heading_count`、图片路径 `image_paths`、Markdown 文件 `markdown_file`。
- **拿不到 `markdown_file` 或 `ok=false` 时**：把错误原样告诉用户（如「未识别到 Word 标题样式」），不要自己臆造内容补齐。
- 若 `heading_count=0`，先提示用户回 Word 给标题套用「标题 1/标题 2」样式再解析——否则章节导航会全部缺失。

### 步骤 2~3：选模板并生成 HTML `[AI]`

按本文档下方的「工作流程」与「硬规则」执行。此两步是**唯一需要审美判断**的环节，不要交给脚本。

**输出 HTML 的硬性技术约定（不遵守会导致第 5 步发布失败或草稿箱格式全丢）**：

- 图片**必须**用本地文件路径（如 `images/图1.png`），**严禁** `base64`（`src="data:image/..."`）或外部 `http(s)` 链接——微信图床不接受前者，会过滤后者。
- 文件必须存为 **UTF-8**，中文直接写入，**禁止** `\uXXXX` 转义（Python 写文件用 `encoding="utf-8"`，`json.dumps` 用 `ensure_ascii=False`）。
- **样式必须全部写成标签上的内联 `style` 属性**。禁止 `<style>` 标签、禁止 `class` 属性、禁止 `<script>`——微信草稿 API 会静默剥离它们，结果是草稿箱里只剩纯文字（真实事故，必踩）。
- 禁止用伪元素（`::before`/`::after`）承载装饰或用 `:hover` 等交互态；装饰请用实体空元素（`<span style="...">`）+ 边框/色块实现。禁止 `position:fixed`、CSS 变量 `var(--x)`、`@font-face`。
- 正文 ≤ 2 万字符且 < 1MB。**超限时不要靠删内容或挪样式到 `<style>` 来解决**，先跑 `minify_inline_html.py` 无损压缩。
- **源文档含代码块（``` 围栏）时，必须整块渲染成图片**（`python scripts/code_image.py <终稿.md> <输出目录> --cols 52`，再按顺序用 `<img>` 引用），详见 `references/code_block_rules.md`。**禁止**把代码写成 `<pre>` 文本、禁止用 `&nbsp;`/`<br>` 手工承载缩进换行、禁止 `word-break:break-all`——微信会折叠源码空白并在字符中间硬折长行，文本代码块在手机上必然错乱（三次真实返工的教训）。代码示例中的长行要在**源码层**拆成物理行（括号边界或 `\` 续行），不要依赖 CSS 兜底。

### 步骤 4：预检 `[脚本]`（三个脚本，顺序执行）

```bash
# 4.1 发布可行性：图片、体积、转义、字段长度
python scripts/verify_html.py /path/to/排版.html --title "标题" --digest "摘要" --author "作者"

# 4.2 微信渲染兼容性：确保样式全内联（最关键，防止草稿箱格式全丢）
python scripts/verify_wechat_compat.py /path/to/排版.html

# 4.3 内容保真反向核验：源文档 vs 排版 HTML
python scripts/verify_fidelity.py /path/to/终稿.md /path/to/排版.html --main-title "文章主标题"
```

- 三个脚本都必须退出码 `0` 才进入第 5 步；否则按 `errors` 逐条修复后重跑。
- `verify_html.py` 拦住：base64 图片、外链图片、图片文件缺失、`\uXXXX` 转义残留、标题/摘要/作者超长、体积超限。
- `verify_wechat_compat.py` 拦住：`<style>`、`class`、`<script>`/`<link>`/`<iframe>`、伪元素、`position:fixed`、CSS 变量、`@font-face`、无内联样式；并对 `<pre>` 文本代码块给出「应转图片」警告。**这是防止「预检通过但格式全丢」的关键关卡，绝不可跳过。**
- `verify_fidelity.py` 拦住：正文段落缺失/多出/错序、数字不一致。历史事故是排版时漏掉了文章开头的两段导语，只能靠它发现。

**体积超限时**（`verify_html.py` 报「正文超限」）：

```bash
python scripts/minify_inline_html.py /path/to/排版.html -o /path/to/排版.min.html
```

- 只做视觉等价的字符级压缩（去空格、`#ffffff`→`#fff`、`0px`→`0`、合并重复样式串），**绝不引入 `<style>`/`class`**。
- 成品视觉完全不变，可放心替换原文件；压缩后需重跑 4.1 和 4.2 确认。

### 步骤 5：发布到草稿箱 `[工具]`

调智能体 `wechat-sop-publish-assistant` 的 `publish_draft` 工具：

```
publish_draft(
  html_path="<第3步的HTML绝对路径>",
  title="<≤32字>",
  cover_path="<封面图本地路径>",
  digest="<可选，≤120字>",
  author="<可选，≤16字>"
)
```

- 封面必须是**本地 jpg/png 文件**（建议 2.35:1）；智能体不做封面自动生成，需要用户提供或用生图工具先生成。
- 该工具只写草稿箱，不群发。
- 需要用户已在智能体设置里配置 AppID/AppSecret，且本机出口 IP 在公众号白名单内。
- **服务端会强制执行和 4.2 一样的兼容性校验**：如果 HTML 里有 `<style>`/`class`，发布会直接被拒绝并返回修复说明（不会再出现「发布成功但格式丢了」）。被拒绝时不要绕过，按提示改成内联样式后重试。
- 也可以单独调 `check_wechat_compat` 工具做兼容性自检（与 4.2 脚本等价）。

### 全流程约束

- **确定性的事交给脚本，审美的事才由你做。** 不要用临时代码重新实现解析、校验、发布——这些已有脚本/工具。
- 每一步的真实产物（文件路径、脚本输出）要展示给用户，不要只说「已完成」。
- 用户只要求其中某一步时（如只要排版），就只做那一步，不要擅自发布。

---

## 工作流程

1. **建立源内容清单**：完整读取正文、标题层级、列表、表格、引用、图片与顺序。不要凭文件名或摘要猜测内容。
2. **分析文章**：识别主题、行业、内容类型、目标读者、传播目的、品牌调性与文章情绪。
3. **选择视觉方案**：读取 `references/style_matrix.md`，确定配色、标题、导航、卡片、引用、图片、分割线与背景纹理的统一组合。用户提供参考案例时，再读取 `references/style_learning_rules.md`。
4. **保护原始内容**：生成前读取 `references/content_fidelity_rules.md`、`references/image_preservation_rules.md` 和 `references/title_navigation_rules.md`。
5. **设计并生成 HTML**：读取 `references/design_principles.md`、`references/wechat_layout_rules.md` 与 `references/visual_elements_library.md`。从 `assets/` 选择并实际使用适合本篇的视觉片段；每篇至少使用 6 类视觉元素，但不得为了凑数量破坏阅读。
6. **四重自检**：按 `references/quality_check.md` 检查内容、图片、视觉与微信移动端适配。任一阻断项失败，先修复再交付。

## 硬规则

- 保持正文 Content Fidelity = 100%；不删、不增、不改、不总结、不重排。
- 第一行文章主标题默认不进入正文 HTML，只用于内容分析、风格判断、封面建议和摘要建议。用户明确要求正文保留时才展示。
- 正文一级、二级、三级标题保留原位置并分别设计。
- 每个含二级标题的一级标题下生成章节导航；导航文字只能逐字复制该章节原有二级标题。
- 原图按原位置和顺序进入 HTML，不得遗漏或用无关图片替换。确实无法提取时，在原位置使用“此处插入原文第 X 张图片”占位并在交付说明中列出。
- 禁止退化为普通标题和段落堆叠。HTML 必须有明确风格、层级、视觉节奏，并至少使用 6 类适配内容的视觉元素。
- **样式只允许内联 `style` 属性**：不得输出 `<style>` 标签、`class` 属性、`<script>`，不得依赖伪元素/交互态/fixed 定位/CSS 变量/外链字体。这是微信平台的硬约束，不是风格偏好。
- 不直接复制第三方模板、专有版式、Logo、插画或标志性视觉资产；只提炼设计语言并进行原创组合。
- 不自动上传、发布、安装依赖或执行外部操作。

## 输出顺序

1. **设计分析**：简述主题、类型、读者、传播目的、视觉风格、配色和主要视觉元素。
2. **HTML 预览代码**：输出完整、移动端优先、以内联 CSS 为主的公众号 HTML。正文只包含源内容、源图片、原标题导航副本和非文字装饰。
3. **运营建议**：在 HTML 外提供封面建议、摘要建议，以及复制到公众号编辑器的方法。CTA、二维码或互动区仅在原文已有对应内容或用户明确要求时写入正文；否则作为可选建议，不混入保真 HTML。
4. **自检结果**：列出内容、图片、主标题、章节导航、视觉元素数量、风格匹配和移动端适配结果。

## 资产使用

- `assets/style_examples/`：完整视觉语言示例，只学习结构并替换为本篇参数。
- `assets/color_palettes/`：角色化配色数据。
- `assets/icons/`：可内联的原创几何图标与装饰。
- `assets/dividers/`：微信兼容的章节分隔组件。
- `assets/card_patterns/`：标题、导航、引用、重点、图片、数据和 CTA 卡片片段。

不要把资产占位文字直接输出；必须替换为对应原文，或在不适用时不使用该组件。
