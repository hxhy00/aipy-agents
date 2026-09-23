# 代码块处理规则（技术类文章必读）

> 来源：2026-09 A2A 协议文章的真实返工教训。三次发布三次错乱后，最终定型为「代码块转图片」方案。

## 为什么代码块是公众号排版的头号坑

微信草稿 API 会对 HTML 做**静默重写**，对代码块的三重打击：

| 微信行为 | 后果 |
|---|---|
| 折叠源码里的换行符 `\n` 和连续空格 | `<pre>` 里的缩进全部丢失，代码挤成一坨 |
| 不保证 `white-space:pre` 语义 | 依赖 CSS 保留空白不可靠 |
| 长行在**字符中间**硬折 | Python 缩进层级被破坏，`break-all` 更是雪上加霜 |

**结论：文本形态的代码块（`<pre>`/`<code>` 段落）在微信里永远不可靠。**

## 三种方案对比（已验证）

| 方案 | 换行缩进 | 高亮 | 可复制 | 结论 |
|---|---|---|---|---|
| A. HTML 文本 + `<br>`/`&nbsp;` 显式承载 | 缩进能保住，但**长行超屏宽必被硬折** | 内联 span 可行 | 可以 | ❌ 长行无解（38 行代码 20 行超 375px 屏宽） |
| B. 精简代码压到每行 ≤ 屏宽 | 可行 | 可行 | 可以 | ⚠️ 只适合极短示例，代码完整度差 |
| C. **整块渲染成图片** | 像素级正确 | 像素级正确 | 不可以 | ✅ **默认方案** |

## 方案 C 实施步骤（用 scripts/code_image.py）

```bash
# 依赖：pip install pygments pillow playwright && playwright install chromium
python scripts/code_image.py /path/to/终稿.md /path/to/out_code --cols 52
```

脚本按代码块出现顺序输出 `code-1.png`、`code-2.png`…，然后在 HTML 里按顺序引用：

```html
<p style="margin:0 0 20px;text-align:center;">
  <img src="out_code/code-1.png" alt="代码示例 1"
       style="max-width:100%;height:auto;border-radius:8px;display:inline-block;" />
</p>
```

发布时 `publish_draft` 会像普通图片一样自动 uploadimg 中转上传。

### code_image.py 的三个关键设计（不要退化）

1. **词法分析用 Pygments**，不要手写正则高亮（手写版会漏 token class，普通标识符 `.n` 被默认浅色主题盖成看不清）。
2. **排版折行交给 Chromium**（Playwright 截图，`device_scale_factor=2` 保证视网膜屏清晰）。
3. **源码层消灭超宽行**：渲染前把长逻辑行在括号边界/续行符处拆成物理行（脚本内置自动列宽探测，逐逻辑行测视觉行数，仍折行就放宽 `cols` 直到零折行）。**绝不允许** `word-break:break-all` 之类的 CSS 兜底。

## 保真核验的配合

- `verify_fidelity.py` 的 `extra` 里若出现代码文本，属预期（源码进图片后 HTML 无对应文字）；但 `missing` 不应有正文段落。
- 正文里引用代码中的数字（如端口号 `9999`）造成的 `number_diff` 可人工确认后放行，需在交付说明中列出。

## 何时可以不用图片

满足**全部**条件时才允许文本代码块：每行 ≤ 40 半角字符、总行数 ≤ 5、无中文注释、单色即可。实践中技术教程几乎不可能满足，默认走图片。
