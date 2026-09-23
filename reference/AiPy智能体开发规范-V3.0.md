# **AiPy 智能体开发规范 V3.0**

北京知道创宇信息技术股份有限公司

2026年7月

## 版本说明

| 创建人 | 修订内容 | 修订时间      | 版本号  | 审阅人 |
| --- | --- |-----------|------| --- |
| 陈余   | 首次建立 | 2026-07-15 | V3.0 |        |

## 文档信息

| 文档名称 | AiPy智能体开发规范（本地单机版/桌面标准版、企业版、网安版合并版） | 文档编号 |  |
| --- |----------------| --- | --- |
| 文档版本号 | V3.0           | 保密级别 | 公开 |
| 扩散范围 |                |  |  |
| 扩散批准人 |                |  |  |

## 文档说明

本文覆盖 AiPy 本地单机版/桌面标准版、企业版、网安版，将列出基本信息并详细介绍智能体开发规范。

## 版权声明

本文件中出现的任何文字叙述、文档格式、插图、照片、方法、过程等内容，除另有特别注明，版权均属北京知道创宇信息技术股份有限公司所有，受到有关产权及版权法保护。任何个人、机构未经北京知道创宇信息技术股份有限公司的书面授权许可，不得以任何方式复制或引用本文件的任何片段。

# **概述**

本文档定义了 AiPy 智能体的开发标准、配置规范和接口约定，覆盖 Node.js 工具调用型、Prompt 提示词注入型、Python 工具型、embed-webview 页面嵌入型和 conversation-embed-view 对话嵌入型等多种类型，并提供完整的示例项目。

# **智能体**

## 定义

在 AiPy 中，智能体是基于 Anthropic DXT（mcpb）规范构建的扩展，以 Streamable HTTP Server 形式运行，为 AI 对话提供工具调用、Prompt 注入等能力增强。

## 支持类型

| 类型 | 关键字 | 类型说明 |
|:---|:---|:---|
| 对话工具 | conversation-tool | 在任务中提供 MCP 工具或 Prompt 能力，主要有Node.js 项目、Prompt 项目、Python项目 3种 对话工具 |
| 内嵌 webview 页面 | embed-webview | 在 AiPy 集市页内以内嵌方式展示页面 |
| 对话页面嵌入页面 | conversation-embed-view | 在 AiPy 对话流中嵌入交互页面 |
| 技能 | skills | 提供工作流或复杂业务逻辑的编排与执行能力，支持多步骤任务的自动化处理流程 |

## 版本说明

智能体区分 **本地单机版/桌面标准版（standalone）**、**企业版（enterprise）** 和 **网安版（cybersecurity）** 三个版本，三者在开发规范上完全相同，区别仅在于组织名和安装目录：

| 版本 | 组织名 | name 格式示例 | 安装目录标识 |
|:-----|:-------|:--------------|:-------------|
| 本地单机版/桌面标准版 | aipy-standalone | @aipy-standalone/filesystem | aipy-standalone |
| 企业版 | aipy-enterprise | @aipy-enterprise/filesystem | aipy-enterprise |
| 网安版 | aipy-cybersecurity | @aipy-cybersecurity/filesystem | aipy-cybersecurity |

开发智能体时，需根据目标版本选择对应的组织名填写 `name` 字段，并安装到对应的目录下。

# **智能体运行环境**

## 安装目录

> **注意：** 本地单机版/桌面标准版目录标识为 `aipy-standalone`，企业版为 `aipy-enterprise`，网安版为 `aipy-cybersecurity`，以下以企业版为例。

| 版本 | 操作系统 | 安装路径 |
|:-----|:---------|:---------|
| 本地单机版/桌面标准版 | Windows | C:\Users\用户名\AppData\Roaming\aipy-standalone\extensions |
| 本地单机版/桌面标准版 | macOS | ~/Library/Application Support/aipy-standalone/extensions |
| 企业版 | Windows | C:\Users\用户名\AppData\Roaming\aipy-enterprise\extensions |
| 企业版 | macOS | ~/Library/Application Support/aipy-enterprise/extensions |
| 网安版 | Windows | C:\Users\用户名\AppData\Roaming\aipy-cybersecurity\extensions |
| 网安版 | macOS | ~/Library/Application Support/aipy-cybersecurity/extensions |

## 目录结构

> **注意：** 本地单机版/桌面标准版组织名为 `@aipy-standalone`，企业版为 `@aipy-enterprise`，网安版为 `@aipy-cybersecurity`，以下以企业版 `@aipy-enterprise` 为例，其余版本替换为对应组织名即可。

```
.../aipy-enterprise/extensions
└── @aipy-enterprise               # 组织名（网安版为 @aipy-cybersecurity）
    └── nodejs                        # 智能体名称--nodejs/prompt 类型
        ├── prompts/                  # prompt 项目存放提示词文件的目录，nodejs 项目根据实际需求确认是否有此目录
        ├── icon.svg                  # 图标文件
        ├── manifest.json             # 入口元数据文件
        └── server.js                 # 服务入口（打包后）
    └── python                        # 智能体名称--python类型
        ├── icon.svg                  # 图标文件
        ├── manifest.json             # 入口元数据文件
        └── main.py                   # 服务入口（打包后）
        └── .python-version           # Python版本（3.12）
        └── pyproject.toml            # Python依赖配置
    └── embed-webview                 # 智能体名称--embed-webview类型
        ├── public/                   # 静态页面存放目录
        │   └── index.html            # 页面入口
        ├── icon.svg                  # 图标文件
        ├── manifest.json             # 入口元数据文件
        └── server.js                 # 服务入口（打包后）
    └── conversation-embed-view       # 智能体名称--conversation-embed-view类型
        ├── public/                   # 前端构建产物目录
        │   └── index.html            # 页面入口（构建生成）
        ├── icon.svg                  # 图标文件
        ├── manifest.json             # 入口元数据文件
        └── server.js                 # 服务入口（打包后）
```

# **智能体开发规范**

## manifest.json 配置规范

manifest.json 是 AiPy 智能体的入口元数据文件。它参考 MCPB 的 manifest.json 规范，但并非所有新增字段都已支持。

### 字段说明

**基础信息字段**

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| dxt_version | string | 是 | DXT版本，当前为 0.1，Skills无需此字段 |
| name | string | 是 | 智能体唯一标识，格式：@组织名/智能体名。组织名根据目标版本填写：本地单机版/桌面标准版填写 `aipy-standalone`，企业版填写 `aipy-enterprise`，网安版填写 `aipy-cybersecurity`。示例：@aipy-standalone/filesystem。智能体名不能与其他智能体重复 |
| display_name | string | 是 | 智能体显示名称，不建议使用与其他智能体相同的智能体显示名称 |
| version | string | 是 | 智能体版本号 |
| description | string | 是 | 智能体功能说明 |
| author | object | 是 | 作者信息，格式：{"name": "AiPy Team"} |
| icon | string | 是 | 图标文件路径，Skills无需此字段 |
| server | object | 是 | 服务的类型、入口配置对象，Skills无需此字段 |
| keywords | array | 是 | 智能体类型关键字（参照2.2章节）。由于DXT不支持扩展字段，目前是在keywords下定义的特殊值来区分智能体在AiPy集市中展示的类型。格式（第一个值为智能体类型关键字（必填），第二个值为智能体在AiPy集市中展示的类型（选填））："keywords": ["conversation-tool", "安全服务"]。 |
| user_config | object | 否 | 用户可配置参数，需要在server.mcp_config配置args或者env中指定填充位置，Skills无需此字段 |
| tools | array | 否 | 智能体对外暴露的可调用的工具，Skills无需此字段 |
| license | string | 否 | 声明智能体的软件许可证类型，Skills无需此字段 |
| prompts | array | 否 | 智能体在集市中点击"去使用"时，自动填充到任务输入框的示例提示词。格式：`[{"name": "示例名称", "text": "示例提示词内容"}]` |

**server 配置字段**

| 字段        | 类型   | 说明                     |
|:------------|:-------|:-------------------------|
| type        | string | 项目类型：node 或 python |
| entry_point | string | 项目入口文件             |
| mcp_config  | object | 项目工具配置对象         |

**mcp_config 配置**

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| command | string | 启动命令（node/uv等） |
| args | array | 命令行参数，支持 `${__dirname}` 和 `${user_config.xxx}` 变量 |
| env | object | 环境变量配置 |

**user_config 配置说明**

如果扩展需要用户填写配置，可以在 manifest.json 里定义 user_config。常见配置类型有：

| 类型        | 说明                          | UI呈现                       |
|:------------|:------------------------------|:-----------------------------|
| type        | 类型：string、number、boolean | 文本输入框/数字输入框/复选框 |
| title       | 配置页面显示的字段名          |                              |
| description | 字段描述说明                  |                              |
| required    | 是否必填                      |                              |

**prompts 配置说明**

如果需要智能体在集市中点击"去使用"时，自动填充示例提示词到任务输入框。可添加 prompts 配置(可参照 Python 项目配置示例)：

| 字段 | 类型   | 必填 | 说明                     |
|:-----|:-------|:-----|:-------------------------|
| name | string | 是   | 示例提示词名称           |
| text | string | 是   | 示例提示词的具体内容，如果提示词需要换行，必须使用 `\n` 代替换行符，需符合 json 格式     |

### Node.js 项目配置示例（工具调用型）

```json
{
    "dxt_version": "0.1",
    "name": "@aipy-enterprise/filesystem",
    "display_name": "Filesystem",
    "version": "1.0.0",
    "description": "filesystem extension for AiPy",
    "author": {
        "name": "AiPy Team"
    },
    "icon": "icon.svg",
    "server": {
        "type": "node",
        "entry_point": "server.js",
        "mcp_config": {
            "command": "node",
            "args": [
                "${__dirname}/server.js"
            ],
            "env": {}
        }
    },
    "keywords": [
        "conversation-tool",
        "安全服务"
    ]
}
```

### Prompt 项目配置示例（纯提示词型）

```json
{
    "dxt_version": "0.1",
    "name": "@aipy-enterprise/prompt",
    "display_name": "Prompt",
    "version": "1.0.0",
    "description": "addition prompt extension for AiPy",
    "author": {
        "name": "AiPy Team"
    },
    "icon": "icon.svg",
    "server": {
        "type": "node",
        "entry_point": "server.js",
        "mcp_config": {
            "command": "node",
            "args": [
                "${__dirname}/server.js"
            ],
            "env": {}
        }
    },
    "keywords": [
        "conversation-tool",
        "安全服务"
    ]
}
```

### Python 项目配置示例

```json
{
    "dxt_version": "0.1",
    "name": "@aipy-enterprise/time",
    "display_name": "Time",
    "version": "1.0.0",
    "description": "time extension for AiPy",
    "author": {
        "name": "AiPy Team"
    },
    "icon": "icon.svg",
    "server": {
        "type": "python",
        "entry_point": "main.py",
        "mcp_config": {
            "command": "uv",
            "args": [
                "run",
                "${__dirname}/main.py"
            ],
            "env": {}
        }
    },
    "prompts": [
        {
          "name": "example",
          "text": "我想要知道当前系统时间：\n 请使用 time 工具获取当前系统时间，并返回结果。"
        }
    ],
    "keywords": [
        "conversation-tool",
        "安全服务"
    ]
}
```

### Skills 项目配置示例

```json
{
    "name": "@aipy-enterprise/skills",
    "display_name": "查找技能",
    "version": "0.0.1",
    "description": "查找技能扩展，支持根据关键词查找和推荐相关技能。",
    "author": {
        "name": "AiPy Team"
    },
    "keywords": [
        "skills",
        "AI 安全"
    ]
}
```

### embed-webview 项目配置示例

```json
{
    "dxt_version": "0.1",
    "name": "@aipy-enterprise/embed-webview",
    "display_name": "内嵌页面示例",
    "version": "1.0.0",
    "description": "embed-webview 类型智能体示例，在 AiPy 集市页内以内嵌 webview 页面展示",
    "author": {
        "name": "AiPy Team"
    },
    "icon": "icon.svg",
    "server": {
        "type": "node",
        "entry_point": "server.js",
        "mcp_config": {
            "command": "node",
            "args": [
                "${__dirname}/server.js"
            ],
            "env": {}
        }
    },
    "keywords": [
        "embed-webview",
        "其他"
    ]
}
```

### conversation-embed-view 项目配置示例

```json
{
    "dxt_version": "0.1",
    "name": "@aipy-enterprise/conversation-embed-view",
    "display_name": "对话嵌入页面示例",
    "version": "1.0.0",
    "description": "conversation-embed-view 类型智能体示例，在 AiPy 对话流中嵌入交互页面，用户操作后可返回结果至对话",
    "author": {
        "name": "AiPy Team"
    },
    "icon": "icon.svg",
    "server": {
        "type": "node",
        "entry_point": "server.js",
        "mcp_config": {
            "command": "node",
            "args": [
                "${__dirname}/server.js"
            ],
            "env": {}
        }
    },
    "keywords": [
        "conversation-embed-view",
        "其他"
    ]
}
```

## 工具开发规范

参数定义：

- Node.js：使用 zod 定义 inputSchema，每个参数需 describe() 说明用途，便于 AI 正确调用

- Python：使用 JSON Schema 格式定义 inputSchema，schema 必须是合法的 JSON Schema 形状

- 参数描述要清晰准确，这是 AI 理解工具用途和正确调用的唯一依据

返回格式（统一使用 content 数组）：

```
// Node.js 统一返回格式
{
content: [
{ type: "text", text: "返回内容" }
]
}

// Python 统一返回格式
[
types.TextContent(type="text", text="返回内容")
]
```

错误处理（不要让异常穿透到框架层）：

1. 捕获异常并返回友好的错误信息，否则在对话里只会看到一个很难理解的失败结果

2. 不要让错误导致服务崩溃，长耗时工具还应补上超时和失败日志

3. 错误信息应包含足够的上下文便于调试，而不是只返回一个笼统的错误码

## 目录结构规范

1.  **Node.js 和 Prompt 项目目录结构相同**:

```
nodejs/
├── node_modules    # 存放安装的依赖目录（构建生成）
├── prompts/        # prompt 项目存放提示词文件的目录，nodejs 项目根据实际需求确认是否有此目录
├── server          # 存放智能体开发代码的服务目录
├── .dxtignore      # 打包排除文件
├── .gitignore      # git排除文件
├── icon.svg        # 智能体图标
├── manifest.json   # 配置文件
├── nodejs.dxt      # 打包生成的dxt文件（打包生成）
├── package.json    # Node.js依赖配置
├── server.js       # 构建生成的单文件（构建生成）
```

2.  **Python 项目：**

```
python/
├── .dxtignore      # 打包排除文件
├── .gitignore      # git排除文件
├── .python-version # Python版本（3.12）
├── icon.svg        # 智能体图标
├── main.py         # 服务主入口
├── manifest.json   # 配置文件
├── pyproject.toml  # Python依赖配置
├── python.dxt      # 打包生成的dxt文件（打包生成）
```

## 代码编写规范

### 端口管理规范

AiPy 会为不同任务启动独立实例，固定端口容易冲突。因此建议使用动态端口分配，不要硬编码端口号：

| 语言             | 实现方式                    | 说明                  |
|:-----------------|:----------------------------|:----------------------|
| Node.js          | app.listen(0)               | Express/Koa 监听端口0 |
| Python (uvicorn) | uvicorn.Config(app, port=0) | 配置port=0由系统分配  |
| Python (fastmcp) | fastmcp run --port 0        | 命令行指定端口0       |

端口信息输出要求（这是 AiPy 接入你服务的前提）：

- 建议输出到 STDOUT（标准输出），而不是 STDERR——AiPy 只从标准输出读取端口信息
- 格式遵循：`{"type": "http_start", "port": 实际端口号}`
- Node.js 通过 `this.address().port` 获取实际端口
- Python 使用 `print(..., flush=True)` 确保立即输出，不要依赖缓冲区自动刷新
- 输出必须是单行有效 JSON，不能有其他日志干扰——这是最容易写错的一点

### 服务输出规范

STDOUT 输出内容建议严格遵循格式要求。这是最容易出错的地方：

| 输出类型 | JSON格式                              | 使用场景       |
|:---------|:--------------------------------------|:---------------|
| 端口启动 | {"type": "http_start", "port": 12345} | 服务启动完成后 |

注意事项：

- 输出前不要有其他日志输出，避免 AiPy 解析失败
- 不要在端口信息前后添加额外字符或换行
- Python 项目注意 uvicorn 默认日志可能干扰 STDOUT 输出，建议在启动阶段调整日志级别或重定向

### capabilities 声明规范

根据项目类型正确声明智能体能力。声明不正确会导致 tools/list 或 prompts/get 报错：

| 项目类型     | capabilities 声明          | 说明               |
|:-------------|:---------------------------|:-------------------|
| 工具调用型   | { tools: {} }              | 仅声明工具能力     |
| 提示词注入型 | { prompts: {}, tools: {} } | 必须同时声明两者   |
| Python工具型 | Server默认支持tools        | 通过装饰器定义工具 |

关键要点：
- 提示词注入型项目必须声明 prompts 能力，否则 Prompt 不会被 AiPy 识别
- 提示词注入型项目需额外注册一个空工具 "_”，避免 tools/list 报错
- Prompt 名称必须为 `addition-system-instruction`，这个名字是固定的

## 模型调用规范（web 智能体）

embed-webview、conversation-embed-view 等 web 智能体需要调用大模型（内容生成、文档解析等）时，统一走 **OpenAI 兼容接口**（`/chat/completions`）。模型地址、密钥等通过环境变量注入，支持 OpenAI、DeepSeek、Anthropic 等任意 OpenAI 兼容服务。以下以企业版「智能标书」（`@aipy-enterprise/tender`，embed-webview 类型）为例说明。

### 环境变量配置

模型调用所需环境变量如下：

| 环境变量 | 获取方式 | 说明 |
|:---|:---|:---|
| MODEL_PROVIDER | AiPy 注入 / .env | 模型提供商前缀，默认 `openai`（如 `openai`/`anthropic`/`deepseek`），用于定位 `${PROVIDER}_BASE_URL`、`${PROVIDER}_API_KEY`、`${PROVIDER}_MODEL` |
| OPENAI_BASE_URL | AiPy 注入 / .env | 模型 API 基础地址，例如 `https://api.openai.com/v1` |
| OPENAI_API_KEY | AiPy 注入 / .env | 模型 API Key |
| OPENAI_MODEL | AiPy 注入 / .env | 模型名称，例如 `gpt-4o` |
| LLM_TLS_REJECT_UNAUTHORIZED | .env（可选） | 模型 HTTPS 调用的证书验证开关，默认 `0`（忽略自签名/内网证书），设为 `1` 恢复证书验证 |

> **AiPy 自动注入：** 智能体在 AiPy 中运行时，AiPy 会在启动进程前自动注入 `MODEL_PROVIDER`、`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`，其值与「设置 - 模型 - 设置为默认模型」中配置的默认模型保持一致。因此 **AiPy 环境下无需任何配置**，智能体启动时直接读取这些环境变量即可调用模型。
>
> **`.env` 仅用于独立测试：** 智能体项目根目录的 `.env` 文件（可参考 `env.example`）只在**脱离 AiPy 独立调试**时使用，例如：
>
> ```
> MODEL_PROVIDER=openai
> OPENAI_BASE_URL=https://api.openai.com/v1
> OPENAI_API_KEY=sk-your-api-key-here
> OPENAI_MODEL=gpt-4o
> LLM_TLS_REJECT_UNAUTHORIZED=0
> ```

### 模型调用实现

下面给出一个精简但完整可用的 OpenAI 兼容客户端，可直接复制使用（带重试、超时、请求日志的完整实现可参考 tender 项目 `lib/llm.js`、`lib/utils.js`）：

```javascript
// 1. 证书验证前置设置：内网管理平台多为自签名证书，默认忽略（对应第 7 章「问题4」）
if (process.env.LLM_TLS_REJECT_UNAUTHORIZED !== "1") {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"
}

// 2. OpenAI 兼容客户端
export class OpenAICompatibleClient {
    constructor({ provider, api_key, base_url, model }) {
        this.provider = provider
        this.apiKey = api_key
        this.apiBaseUrl = base_url
        this.model = model
    }

    // 非流式：返回完整文本，内容取 choices[0].message.content
    async completions(messages) {
        const response = await fetch(`${this.apiBaseUrl}/chat/completions`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${this.apiKey}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ model: this.model, messages })
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`)
        const result = await response.json()
        return result.choices?.[0]?.message?.content || ""
    }

    // 流式：请求体追加 stream:true，返回 SSE Response，增量取 choices[0].delta.content
    async completionsStream(messages) {
        const response = await fetch(`${this.apiBaseUrl}/chat/completions`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${this.apiKey}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ model: this.model, messages, stream: true })
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`)
        return response
    }
}

// 3. 服务启动时创建客户端（从环境变量读取配置）
export function createLLMClient() {
    const provider = (process.env.MODEL_PROVIDER || "openai").toUpperCase()
    return new OpenAICompatibleClient({
        provider,
        api_key: process.env[`${provider}_API_KEY`],
        base_url: process.env[`${provider}_BASE_URL`],
        model: process.env[`${provider}_MODEL`],
    })
}

// 4. 解析 OpenAI 兼容 SSE 流，逐段产出增量文本（遇 data: [DONE] 结束）
export async function* parseLLMStream(response) {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() || ""
        for (const line of lines) {
            if (!line.startsWith("data: ")) continue
            const data = line.slice(6).trim()
            if (data === "[DONE]") return
            try {
                const delta = JSON.parse(data).choices?.[0]?.delta?.content || ""
                if (delta) yield delta
            } catch { /* 忽略解析异常 */ }
        }
    }
}
```

### 使用示例

非流式调用：

```javascript
const llm = createLLMClient()
const content = await llm.completions([
    { role: "system", content: "系统提示词" },
    { role: "user", content: "用户输入内容" }
])
```

流式调用（增量文本可经 SSE 实时转发给前端页面）：

```javascript
const llm = createLLMClient()
const response = await llm.completionsStream([
    { role: "system", content: "系统提示词" },
    { role: "user", content: "用户输入内容" }
])
for await (const delta of parseLLMStream(response)) {
    // delta 为增量文本
}
```

# **项目构建、打包、安装使用**

## 构建

### 构建概览

| 项目类型            | 是否需要构建 | 构建工具 |
|:--------------------|:-------------|:---------|
| Node.js 工具调用型  | 是           | bun      |
| Prompt 提示词注入型 | 是           | bun      |
| Python 项目         | 否           | 无需构建 |
| Skills 项目         | 否           | 无需构建 |
| embed-webview 项目  | 是           | bun      |
| conversation-embed-view 项目 | 是  | bun |

Node.js 、 Prompt 、 embed-webview 、 conversation-embed-view 项目的构建流程相同：
- 使用 bun 工具
- 构建为单文件(conversation-embed-view/embed-webview还会生成public文件夹，存放页面代码) server.js，减少依赖

### Node.js/Prompt 项目构建

Node.js 工具调用型、 Prompt 提示词注入型项目的构建流程完全相同。下面以 Node.js 项目为例。

**构建步骤：推荐使用bun**

1. 安装依赖：执行后安装项目需要的依赖，在当前项目根目录生成node_modules文件夹
```
bun install
```

2. 构建单文件 server.js ：执行后在当前项目根目录生成一个server.js文件，与 manifest.json 中的entry_point 保持一致
```
bun run build
```

**构建产物结构：**

```
# 构建后的项目结构
nodejs/
├── node_modules    # 存放安装的依赖目录（新增）
├── prompts/        # prompt 项目存放提示词文件的目录，nodejs 项目根据实际需求确认是否有此目录
├── server
├── .dxtignore
├── .gitignore
├── icon.svg
├── manifest.json
├── package.json
├── server.js       # 构建生成的单文件（新增）
```

### Python 项目构建

Python 项目无需构建步骤，依赖 uv 自动管理，跳过此步骤，直接打包即可。

### embed-webview 项目构建

embed-webview 项目构建流程与 Node.js 项目类似，只需构建后端服务入口。

**构建步骤：**

1. 安装依赖：
```
bun install
```

2. 构建单文件 server.js：
```
bun run build
```

**构建产物结构：**

```
# 构建后的项目结构
embed-webview/
├── public/            # 静态页面目录
│   └── index.html     # 页面入口
├── .dxtignore
├── .gitignore
├── icon.svg
├── index.js           # 服务入口源码
├── manifest.json
├── package.json
├── server.js          # 构建生成的单文件（新增）
```

### conversation-embed-view 项目构建

conversation-embed-view 项目需要双构建流程：先构建前端页面，再构建后端服务入口。

**构建步骤：**

1. 安装依赖：
```
bun install
```

2. 执行构建（包含前端和后端）：
```
bun run build
```

构建脚本会依次执行：
- 前端构建：将 `src/client/` 构建到 `public/` 目录（使用 bun-plugin-tailwind）
- 后端构建：将 `src/server/index.js` 构建为单文件 `server.js`

**构建产物结构：**

```
# 构建后的项目结构
conversation-embed-view/
├── public/                # 前端构建产物（新增）
│   └── index.html         # 页面入口
├── src/
│   ├── server/            # 服务端源码
│   └── client/            # 前端源码
├── .dxtignore
├── .gitignore
├── build.js               # 前端构建脚本
├── icon.svg
├── manifest.json
├── package.json
├── server.js              # 构建生成的单文件（新增）
```

### Skills 项目构建

Skills 项目无需构建步骤，跳过此步骤，直接打包即可。

## 打包

### 打包概览

1.  **通用打包命令dxt pack ：**
```
# 用法
npx @anthropic-ai/dxt pack
```

2.  **打包原理（.dxt 本质就是 zip）：**
- 读取 manifest.json 获取智能体元信息
- 解析 .dxtignore 排除指定文件
- 将剩余文件打包为 zip 格式（.dxt 即 zip）
- 可通过解压工具查看 .dxt 文件内容

3.  **.dxtignore文件：**

.dxtignore 用来排除不应进入扩展包的文件。建议正确配置，避免把开发阶段的冗余文件打进包里：

| 项目类型 | 排除的文件/目录                               | 说明            |
|:---------|:----------------------------------------------|:----------------|
| Node.js  | package.json, bun.lock, server/, node_modules | 排除源码和依赖  |
| Prompt   | package.json, bun.lock, server/, node_modules | 排除源码和依赖  |
| Python   | .venv,uv.lock                                 | 排除虚拟环境    |
| embed-webview | node_modules, bun.lock, index.js, README.md | 排除源码和依赖  |
| conversation-embed-view | /bun.lock, /src, /node_modules, /build.js, /eslint.config.js, /*.dxt, README.md | 排除源码、依赖和构建脚本 |
| 通用     | .gitignore, .git                              | 排除Git相关文件 |

4.  **打包必须包含的文件：**

| 项目类型 | 必须包含的文件/目录 | 说明 |
|:---|:---|:---|
| Node.js | icon.svg,manifest.json,server.js | 智能体图标、入口清单文件、最终运行所需的入口文件 |
| Prompt | icon.svg,manifest.json,server.js,prompts/ | 智能体图标、入口清单文件、最终运行所需的入口文件、提示词目录 |
| Python | icon.svg,manifest.json,main.py,.python-version,pyproject.toml | 智能体图标、入口清单文件、最终运行所需的入口文件、Python版本、Python依赖配置文件 |
| embed-webview | icon.svg,manifest.json,server.js,public/ | 智能体图标、入口清单文件、最终运行所需的入口文件、静态页面目录 |
| conversation-embed-view | icon.svg,manifest.json,server.js,public/ | 智能体图标、入口清单文件、最终运行所需的入口文件、前端构建产物目录 |

### Node.js/Prompt 项目打包

Node.js 工具调用型和 Prompt 提示词注入型项目的打包流程完全相同。下面以 Node.js 项目为例。

**打包步骤：**

1.  执行以下打包命令生成dxt文件：
```
npx @anthropic-ai/dxt pack
```

**打包说明（这一步产出一个可安装的 .dxt 文件）：**
- 读取 manifest.json 获取扩展元信息，解析 .dxtignore 排除指定文件
- 将剩余文件打包为 .dxt 格式（.dxt 本质就是 zip）
- 输出文件名格式：项目名称.dxt（如 nodejs.dxt）

**打包产物结构：**

```
# 打包后的项目结构
nodejs/
├── node_modules
├── prompts/            # prompt 项目存放提示词文件的目录，nodejs 项目根据实际需求确认是否有此目录
├── server
├── .dxtignore
├── .gitignore
├── icon.svg
├── manifest.json
├── nodejs.dxt          # 打包生成的dxt文件
├── package.json
├── server.js
```

### Python 项目打包

**打包步骤：**

1. 安装依赖（可选，uv run 会自动处理，调试时可以在本地执行此命令安装依赖测试项目，正式打包时，跳过此步骤）：
```
uv sync
```

2. 执行以下打包命令生成dxt文件
```
npx @anthropic-ai/dxt pack
```

**打包说明（这一步产出一个可安装的 .dxt 文件）：**
- 读取 manifest.json 获取扩展元信息，解析 .dxtignore 排除指定文件
- 将剩余文件打包为 .dxt 格式（.dxt 本质就是 zip）
- 输出文件名格式：项目名称.dxt（如 python.dxt）

**打包产物结构：**

```
# 打包后的项目结构
python/
├── .dxtignore
├── .gitignore
├── .python-version
├── icon.svg
├── main.py
├── manifest.json
├── pyproject.toml
├── python.dxt          # 打包生成的dxt文件
```

### embed-webview 项目打包

**打包步骤：**

1. 执行构建命令生成 server.js：
```
bun run build
```

2. 执行打包命令生成 dxt 文件：
```
npx @anthropic-ai/dxt pack
```

**打包说明：**
- 读取 manifest.json 获取扩展元信息，解析 .dxtignore 排除指定文件
- 将剩余文件打包为 .dxt 格式
- 输出文件名格式：项目名称.dxt（如 embed-webview.dxt）

**打包产物结构：**

```
# 打包后的项目结构
embed-webview/
├── public/
│   └── index.html
├── .dxtignore
├── .gitignore
├── icon.svg
├── index.js           
├── manifest.json
├── package.json       
├── server.js
├── embed-webview.dxt  # 打包生成的dxt文件
```

### conversation-embed-view 项目打包

**打包步骤：**

1. 执行构建命令（包含前端和后端构建）：
```
bun run build
```

2. 执行打包命令生成 dxt 文件：
```
npx @anthropic-ai/dxt pack
```

**打包说明：**
- 前端构建产物在 `public/` 目录下
- 后端构建产物为单文件 `server.js`
- .dxtignore 排除源码目录 `src/` 和构建脚本 `build.js`

**打包产物结构：**

```
# 打包后的项目结构
conversation-embed-view/
├── public/                # 前端构建产物
│   └── index.html
├── src/                   
├── .dxtignore
├── .gitignore
├── build.js               
├── icon.svg
├── manifest.json
├── package.json           
├── server.js
├── conversation-embed-view.dxt  # 打包生成的dxt文件
```

### Skills 项目打包

**打包步骤：**
1. Skills设置完成后，无需其他处理，使用zip压缩项目文件夹为zip格式文件即可，可使用以下命令打包：
```
zip -r skills.zip . # skills.zip修改为实际准备打包的名字
```

**打包说明（这一步产出一个可安装的 .zip 文件）：**
- 使用zip命令把当前Skills 项目下的文件都打到zip压缩包中
- 输出文件名格式：项目名称.zip（如 skills.zip）

**打包产物结构：**

```
# 打包后的项目结构
skills/
├── manifest.json
├── SKILL.md
├── skills.zip      # 打包生成的zip文件
```

## 验证

1. 打包完成后，建议通过以下方式验证 dxt 文件完整性：
- manifest.json 是否包含在包内
- 入口文件（server.js/main.py）是否包含在包内
- 运行时依赖的资源文件是否完整
- 是否误将虚拟环境或源码垃圾文件打包

2. 建议执行 unzip -p your-agent.dxt manifest.json 验证 manifest.json 内容是否正确

3. Skills 项目使用unzip -p skills.zip 查看项目中的文件是否都被压缩到zip文件中

## 调试

### 进程启动检查

建议首先确认以下基础项：
- AiPy 是否成功拉起扩展进程
- 入口文件是否能正常执行
- 关键环境变量是否已配置

### 启动阶段日志

建议在入口文件最早阶段输出以下信息：
- 版本号
- 关键环境变量是否存在
- 入口参数
- 当前启动分支

注意：不要将敏感密钥完整打印到日志中。如需调试，建议仅打印"是否存在"及密钥长度

### 打包产物检查

很多“本地能跑、安装后不能跑”的问题大都来自打包产物不完整。

建议优先检查：
- 入口文件是否被打包进 dxt 文件
- 依赖文件在运行时是否可用
- 构建产物路径是否与 manifest.json 中 entry_point 一致

### 本地入口验证

在排查 AiPy 问题前，建议先本地直接运行入口进程验证：

Python：
```
uv run main.py
```

Node.js：
```
node server.js
```
如果入口在本地都无法启动，建议优先解决入口自身问题。

## 发布

将 .dxt/.zip 文件安装到 AiPy 的方式有两种，本地安装和管理平台集市安装

### 本地安装

1. **导入智能体(Node.js/Prompt/Python/embed-webview/conversation-embed-view)：**
- 在 AiPy 集市界面，点击【选择智能体安装】按钮，选择 .dxt 文件 导入
- AiPy 会自动解压并安装该智能体
- 安装好后，智能体集市列表展示该智能体的卡片

2.  **导入技能（Skills）：**
- 在 AiPy 集市界面，点击【Skills】- 【从文件安装】按钮，选择 zip 文件 导入
- AiPy 会自动解压并安装该skills
- 安装好后，智能体集市列表展示该Skills的卡片

### 管理平台集市安装
- 登录到AiPy管理平台管理平台，进入集市管理，上传智能体，配置智能体信息，选择需要上传的智能体文件，上传
- 上传完成后，在集市管理列表展示该智能体
- 打开AiPy 客户端，进入设置-常规界面，配置管理平台内网IP
- 打开AiPy 客户端集市，找到该智能体，并安装
- AiPy 会安装该智能体到本地，安装完成后，显示已安装

### 安装完成

**安装后的目录结构：**

```
# 安装后的智能体目录示例（以企业版为例，网安版目录为 @aipy-cybersecurity）
.../extensions/@aipy-enterprise/
├── filesystem/
│   ├── icon.svg
│   ├── manifest.json
│   └── server.js
├── prompt/
│   ├── prompts/              # prompt 项目存放提示词文件的目录
│   ├── icon.svg
│   ├── manifest.json
│   └── server.js
└── time/
    ├── icon.svg
    ├── manifest.json
    ├── main.py
    ├── pyproject.toml
    └── .python-version
├── embed-webview/
│   ├── public/               # 静态页面目录
│   │   └── index.html        # 页面入口
│   ├── icon.svg
│   ├── manifest.json
│   └── server.js
├── conversation-embed-view/
│   ├── public/               # 前端构建产物目录
│   │   └── index.html        # 页面入口
│   ├── icon.svg
│   ├── manifest.json
│   └── server.js
```

# **智能体开发最佳实践**

本章提供智能体开发的完整流程指导和示例项目。建议先阅读前面章节了解技术细节，再参考本章内容进行开发。推荐按以下步骤进行：确定智能体类型、获取项目示例代码、编写最小配置清单、验证入口进程、接入业务逻辑、构建打包、验证、发布。

本章提供多种类型的完整示例项目，分别展示工具调用型、Prompt 提示词注入型、Python 工具型、embed-webview 页面嵌入型和 conversation-embed-view 对话嵌入型智能体的开发模式。

## 开发环境准备

**Node22.22.2安装：**
- 下载地址：<https://nodejs.org/zh-cn/download>
- 验证命令：node --version

**npm安装：**
- 一般是跟随node一起安装，不用单独安装
- 验证命令：npm --version

**bun安装：**
- 安装文档：<https://bun.sh/docs/installation>
- 验证命令：bun --version

**Python3.12安装：**
- 下载地址：<https://www.python.org/downloads/release/python-31211/>
- 安装文档：<https://docs.python.org/zh-cn/3.12/using/index.html>
- 验证命令：python --version

## 确定智能体类型

根据2.2章节确认即将开发的智能体类型。

## 获取项目示例代码

根据智能体类型获取对应示例代码，注意事项参见6.2.1-6.2.5章节。

### Node.js 项目示例（工具调用型）

**项目示例代码：** 参考 `项目示例代码/node` 下的代码。
**项目说明：** 这是一个文件读取智能体，在使用时，可以发起提问 “帮我读取C:\project\nodejs\package.json 这个的文件内容” ，文件路径替换为真实文件路径。

**项目结构：**

```
nodejs/
├── .dxtignore          # 打包排除文件
├── .gitignore
├── bun.lock
├── icon.svg            # 智能体图标
├── manifest.json       # 配置文件，配置参照4.1章节 manifest.json 配置规范
├── package.json        # Node.js依赖配置
├── server/
│ ├── index.js          # 服务主入口
│ └── tools/
│ └── read-file.js      # 工具实现
```

**package.json 配置：**
```json
{
    "type": "module",
    "private": true,
    "scripts": {
        "build": "rolldown server/index.js --minify --platform=node --format=esm --file=server.js",
        "pack": "npm run build && dxt pack"
    },
    "dependencies": {
        "@modelcontextprotocol/sdk": "^1.24.2",
        "zod": "^4.1.13"
    },
    "devDependencies": {
        "@anthropic-ai/dxt": "^0.2.6",
        "rolldown": "^1.0.0-beta.53"
    }
}
```

**服务入口 server/index.js：**

```javascript
#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js"
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js"
import pkg from "../manifest.json" with { type: "json" }
import * as readFile from "./tools/read-file.js"

const app = createMcpExpressApp()

app.post("/mcp", async (req, res) => {
    const server = getServer()
    try {
        const transport = new StreamableHTTPServerTransport({
            sessionIdGenerator: undefined,
        })
        await server.connect(transport)
        await transport.handleRequest(req, res, req.body)
        res.on("close", () => {
            transport.close()
            server.close()
        })
    } catch (error) {
        console.error("Error handling MCP request:", error)
        if (!res.headersSent) {
            res.status(500).json({
                jsonrpc: "2.0",
                error: { code: -32603, message: "Internal server error" },
                id: null
            })
        }
    }
})

// 监听端口 0，随机选择端口，需符合4.4.1章节 端口管理规范
app.listen(0, function (err) {
    if (err) {
        console.error("Failed to start server:", err)
        process.exit(1)
    }
    // 输出监听的端口号，需符合4.4.1、4.4.2章节 端口管理规范、服务输出规范
    console.log(JSON.stringify({
        "type": "http_start",
        "port": this.address().port
    }))
})

function getServer() {
    const server = new McpServer(
        { name: pkg.name, version: pkg.version },
        // 声明智能体能力，需符合4.4.3章节 capabilities 声明规范
        { capabilities: { tools: {} } }
    )
    // 注册工具
    server.registerTool(readFile.toolDefinition.name, readFile.toolDefinition, readFile.handler)
    return server
}

process.on("SIGINT", async () => {
    console.log("Server shutdown complete")
    process.exit(0)
})
```

**工具实现 server/tools/read-file.js：**

```javascript
import fs from "node:fs/promises"
import * as z from "zod/v4"

export const toolDefinition = {
    name: "read_file",
    description: "Read Text File",
    inputSchema: {
        // 参数定义，需符合4.2章节 工具开发规范
        filePath: z.string().describe("Path to the file to be read"),
        encoding: z.string().optional().describe("File encoding, default is 'utf-8'"),
    },
}

export async function handler({ filePath, encoding = "utf-8" }) {
    return {// 返回格式，需符合4.2章节 工具开发规范
        content: [
            {
                type: "text",
                text: await fs.readFile(filePath, encoding)
            }
        ]
    }
}
```

**.dxtignore 配置：**

```
// 需符合5.2.1章节 打包概览
package.json
bun.lock
server
node_modules
```

### Prompt 项目示例（ 纯提示词型）

**项目示例代码：** 参考 `项目示例代码/prompt` 下的代码。

**项目说明：** 这是一个文档生成智能体，将用户输入转换为结构良好的文档格式。在使用时，可以让这个智能体将输入内容整理成文档。

**项目结构：**

```
prompt/
├── .dxtignore
├── .gitignore
├── prompts/            # prompt 项目存放提示词文件的目录
├── icon.svg
├── manifest.json       # 配置文件，配置参照4.1章节 manifest.json 配置规范
├── package.json
├── server/
│ └── index.js
```

**package.json 配置：**

与 Node.js 工具调用型项目相同，依赖配置一致。

**服务入口 server/index.js（关键代码）：**

```javascript
#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js"
import { createMcpExpressApp } from "@modelcontextprotocol/sdk/server/express.js"
import pkg from "../manifest.json" with { type: "json" }

const app = createMcpExpressApp()

// ... HTTP 路由处理同 Node.js 项目 ...

function getServer() {
    const server = new McpServer(
        { name: pkg.name, version: pkg.version },
        // 申明服务有 Prompt 智能体能力（必须同时声明 tools），需符合4.4.3章节 capabilities 声明规范
        { capabilities: { prompts: {}, tools: {} } }
    )

    // 添加一个空工具避免 tools/list 报错
    server.registerTool("_", {}, () => {})

    // 注册系统提示词
    server.registerPrompt(
        // Prompt 名称必须为 addition-system-instruction，需符合4.4.3章节 capabilities 声明规范
        "addition-system-instruction",
        { description: "document generation prompt" },
        () => {
            return {
                "description": "document generation prompt",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": `
Document Generation Instructions:
You are a document generation AI. Your task is to convert the user's input into a well-structured document format. Follow these guidelines:

1. Understand the Content:
   - Carefully read and comprehend the user's input.
2. Structure the Document:
   - Organize the content into sections with clear headings.
3. Formatting:
   - Ensure consistent formatting throughout.
4. Clarity and Conciseness:
   - Write in a clear and concise manner.
5. Review:
   - Double-check for any grammatical errors or typos.
                            `.trimStart()
                        }
                    }
                ]
            }
        }
    )
    return server
}

process.on("SIGINT", async () => {
    console.log("Server shutdown complete")
    process.exit(0)
})
```

**.dxtignore 配置：**

```
// 需符合5.2.1章节 打包概览
package.json
bun.lock
server
node_modules
```

### Python 项目示例

**项目示例代码：** 参考 `项目示例代码/python` 下的代码。

**项目说明：** 这是一个时间获取智能体。在使用时，可以让这个智能体获取当前时间。

**项目结构：**

```
python/
├── .dxtignore
├── .gitignore
├── .python-version         # Python版本（3.12）
├── icon.svg
├── main.py                 # 服务主入口
├── manifest.json           # 配置文件，配置参照4.1章节 manifest.json 配置规范
├── pyproject.toml          # Python依赖配置
```

**pyproject.toml 配置：**
```
[project]
name = "time"
version = "0.1.0"
description = "time info extension for aipy"
requires-python = ">=3.12"
dependencies = [
"mcp>=1.23.1",
"pytz>=2025.2",
"starlette>=0.50.0",
"uvicorn>=0.38.0",
]
```

**.python-version：**
```
3.12
```

**服务入口 main.py：**

```python
import asyncio
import socket
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
app = Server("time_server", version="1.0.0")

@app.call_tool()  # 声明智能体能力，需符合4.4.3章节 capabilities 声明规范
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.ContentBlock]:
    if name == "current_time":
        import pytz
        from datetime import datetime

        timezone_str = arguments.get("timezone", "UTC")
        try:
            timezone = pytz.timezone(timezone_str)
        except pytz.UnknownTimeZoneError:
            return [  # 返回格式，需符合4.2章节 工具开发规范
                types.TextContent(
                    type="text",
                    text=f"Unknown timezone: {timezone_str}",
                )
            ]

        current_time = datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S %Z%z")
        return [
            types.TextContent(
                type="text",
                text=f"Current time in {timezone_str}: {current_time}",
            )
        ]

    return [
        types.TextContent(
            type="text",
            text=f"Tool '{name}' not recognized.",
        )
    ]

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="current_time",
            description="Get the current time from the server",
            inputSchema={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone (e.g., 'UTC', 'America/New_York')",
                    },
                },
            },
        )
    ]

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    session_manager = StreamableHTTPSessionManager(
        app=app,
        json_response=True,
    )

    async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            logger.info("Application started with StreamableHTTP session manager!")
            try:
                yield
            finally:
                logger.info("Application shutting down...")

    starlette_app = Starlette(
        debug=True,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    starlette_app = CORSMiddleware(
        starlette_app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE"],
        expose_headers=["Mcp-Session-Id"],
    )

    import uvicorn

    # 监听端口 0，随机选择端口，需符合4.4.1章节 端口管理规范
    config = uvicorn.Config(starlette_app, host="127.0.0.1", port=0)
    server = uvicorn.Server(config)

    original_startup = server.startup

    async def patched_startup(sockets: list[socket.socket] | None = None):
        await original_startup(sockets)
        for s in server.servers:
            for sock in s.sockets:
                # 输出监听的端口号，需符合4.4.1、4.4.2章节 端口管理规范、服务输出规范
                print(json.dumps({"type": "http_start", "port": sock.getsockname()[1]}), flush=True)
                return

    server.startup = patched_startup
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```

**.dxtignore：**

```
# 需符合5.2.1章节 打包概览
.venv
uv.lock
```

### embed-webview 项目示例

**项目示例代码：** 参考 `项目示例代码/embed-webview` 下的代码。

**项目说明：** 这是一个待办清单智能体，在 AiPy 集市页内以 iframe 展示。支持添加任务、标记完成、删除任务、筛选、清除已完成等功能，数据使用 localStorage 本地存储。

**项目结构：**

```
embed-webview/
├── .dxtignore          # 打包排除文件
├── .gitignore          # git排除文件
├── icon.svg            # 智能体图标
├── index.js            # 服务入口源码
├── manifest.json       # 配置文件，配置参照4.1章节 manifest.json 配置规范
├── package.json        # Node.js依赖配置
├── README.md           # 项目说明
└── public/
    └── index.html      # 待办清单页面
```

**package.json 配置：**
```json
{
  "name": "@aipy-enterprise/embed-webview",
  "version": "1.0.0",
  "description": "embed-webview 示例项目 - 在 AiPy 中嵌入静态页面",
  "main": "index.js",
  "type": "module",
  "scripts": {
    "build": "bun build --outfile=server.js --production --target=node ./index.js"
  },
  "dependencies": {
    "express": "^5.2.1"
  }
}
```

**服务入口 index.js：**

```javascript
import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

// 兼容打包后的 __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();

// 静态文件服务 - 提供 public 目录下的 HTML/CSS/JS 文件
app.use(express.static(path.join(__dirname, 'public')));

// 启动服务 - 监听端口 0，由系统随机分配，需符合4.4.1章节 端口管理规范
const server = app.listen(0, () => {
  // 输出端口信息，需符合4.4.2章节 服务输出规范
  console.log(JSON.stringify({
    type: 'http_start',
    port: server.address().port
  }));
});

// 优雅退出
process.on('SIGINT', () => {
  console.log('Server shutdown complete');
  process.exit(0);
});
```

**.dxtignore 配置：**

```
# 需符合5.2.1章节 打包概览
node_modules
bun.lock
.DS_Store
index.js
README.md
```

**页面主题适配说明：**

页面需支持根据 URL 参数 `colorScheme` 切换主题：
- `colorScheme=light` → 亮色主题
- 其他值（如 `dark`）→ 暗色主题

示例代码：
```javascript
// 根据 URL 参数 colorScheme 自动切换主题
(function() {
  var urlParams = new URLSearchParams(window.location.search);
  var colorScheme = urlParams.get('colorScheme');
  var theme = colorScheme === 'light' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', theme);
})();
```

### conversation-embed-view 项目示例

**项目示例代码：** 参考 `项目示例代码/conversation-embed-view` 下的代码。

**项目说明：** 这是一个信息收集表单智能体，在对话流中嵌入交互页面。用户填写信息提交后，调用 AiPy API 创建任务并导航到新页面，然后关闭嵌入页面返回对话流。

**项目结构：**

```
conversation-embed-view/
├── .dxtignore          # 打包排除文件
├── .gitignore          # git排除文件
├── build.js            # 前端构建脚本
├── icon.svg            # 智能体图标
├── manifest.json       # 配置文件，配置参照4.1章节 manifest.json 配置规范
├── package.json        # Node.js依赖配置
├── README.md           # 项目说明
└── src/
    ├── server/
    │   ├── index.js        # 服务主入口
    │   └── handlers/
    │       └── submit-form.js  # 表单提交处理
    └── client/
        ├── index.html      # 页面入口
        ├── index.js        # 前端入口
        └── elements/
            ├── index.js        # 自定义元素注册
            └── form-view.js    # 表单组件
```

**package.json 配置：**
```json
{
  "name": "@aipy-enterprise/conversation-embed-view",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "prebuild": "rm -rf public server.js",
    "build": "bun build.js && bun build --outfile=server.js --production --target=node ./src/server/index.js",
    "prepack": "bun run build",
    "pack": "bun x @anthropic-ai/dxt pack"
  },
  "dependencies": {
    "express": "^4.18.2"
  },
  "devDependencies": {
    "bun-plugin-tailwind": "^0.1.2",
    "squark": "^2.0.4",
    "tailwindcss": "^4.1.18"
  }
}
```

**前端构建脚本 build.js：**

```javascript
import tailwind from "bun-plugin-tailwind";

await Bun.build({
  entrypoints: ["src/client/index.html"],
  outdir: "./public",
  plugins: [tailwind],
  minify: true,
});
```

**服务入口 src/server/index.js：**

```javascript
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

// 监听端口 0，由系统随机分配，需符合4.4.1章节 端口管理规范
app.listen(process.env.NODE_ENV === "production" ? 0 : 8000, function () {
  // 输出端口信息，需符合4.4.2章节 服务输出规范
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
```

**表单提交处理 src/server/handlers/submit-form.js：**

```javascript
const AIPY_CLIENT_API = process.env.AIPY_CLIENT_API
const AIPY_CLIENT_API_KEY = process.env.AIPY_CLIENT_API_KEY

/** @type {import("express").RequestHandler} */
export async function submitForm(req, res) {
  try {
    const { name, email, message } = req.body

    // 验证必填字段
    if (!name || !email) {
      return res.status(400).json({ error: "姓名和邮箱为必填项" })
    }

    // 构造任务指令
    const instruction = `用户提交了信息收集表单：
- 姓名：${name}
- 邮箱：${email}
- 备注：${message || "无"}

请根据以上信息执行后续任务。`

    console.log("Sending task to AiPy...")

    // 调用 AiPy API 创建任务
    const createRes = await fetch(`${AIPY_CLIENT_API}/api/aipy/create-task`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${AIPY_CLIENT_API_KEY}`
      },
      body: JSON.stringify([{ instruction }])
    })

    if (!createRes.ok) {
      throw new Error(`创建任务失败: ${await createRes.text()}`)
    }

    const createData = await createRes.json()
    const taskId = createData.data

    console.log(`Task created: ${taskId}`)

    // 导航到新创建的任务页面
    const navigateRes = await fetch(`${AIPY_CLIENT_API}/api/browser/navigate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${AIPY_CLIENT_API_KEY}`
      },
      body: JSON.stringify([`/task/${taskId}`])
    })

    if (!navigateRes.ok) {
      console.error(`导航失败: ${await navigateRes.text()}`)
    }

    // 发送关闭嵌入页面消息，需符合conversation-embed-view特殊规范
    console.log(JSON.stringify({
      type: "client/conversation-embed-view",
      action: "close"
    }))

    // 延迟退出，确保消息已发送
    setTimeout(() => {
      process.exit(0)
    }, 300)

    res.json({ success: true, message: "任务已下发", taskId })
  } catch (error) {
    console.error("Submit failed:", error)
    res.status(500).json({ error: error.message })
  }
}
```

**.dxtignore 配置：**

```
# 需符合5.2.1章节 打包概览
/bun.lock
/src
/node_modules
/build.js
/eslint.config.js
/*.dxt
README.md
```

**conversation-embed-view 特殊注意事项：**

1. **环境变量依赖**：需要使用 `AIPY_CLIENT_API` 和 `AIPY_CLIENT_API_KEY` 环境变量调用 AiPy API

2. **关闭页面消息**：用户操作完成后，需通过 STDOUT 输出以下格式的消息关闭嵌入页面：
```javascript
console.log(JSON.stringify({
  type: "client/conversation-embed-view",
  action: "close"
}))
```

3. **前端技术栈**：使用 Web Components (SquarkElement) + Tailwind CSS，页面需自适应容器大小（height: 100vh）

4. **开发模式端口**：开发环境监听固定端口 8000，生产环境使用动态端口 0

### Skills 项目示例

**项目示例代码：** 参考 `项目示例代码/skills` 下的代码

**项目说明：** 这是一个查找skills的智能体。支持根据关键词查找和推荐相关技能。

**项目结构：**
```
skills/
├── manifest.json # 配置文件，配置参照4.1章节 manifest.json 配置规范
├── SKILL.md # skill文件
├── skills.zip # 打包生成的zip文件
```

## 编写最小配置清单

根据4.1章节修改manifest.json文件，需修改以下字段：
- name
- display_name
- version
- icon
- server
- keywords

## 验证入口进程

此阶段无需实现完整业务逻辑，仅确认以下内容：
- AiPy 能启动进程
- 入口路径正确
- 必需环境变量能读取到

## 接入业务逻辑

将智能体的业务逻辑代码逐步集成到项目中。

## 打包自验证

建议在完成智能体业务逻辑后，进行一次完整的构建、打包、入口验证、安装、使用。验证通过后再继续新增业务逻辑。

## 发布

完成智能体的完整开发、打包、验证后，发布到管理平台管理平台集市。

## 实际案例

### 创宇安全智脑IP情报（Node.js 项目）

**项目示例代码：** 参考 实际案例代码/gac 下的代码。

**项目说明：** 创宇安全智脑IP情报智能体，在使用前，需要先配置 智脑API Key；使用时，可以发起提问“帮我查询192.168.1.11 的情报信息”，IP地址替换为需查询的IP。

**项目结构：**

```
gac/
├── prompts/                                # 提示词目录
│ ├── addition-system-instruction.txt       # 提示词存放文件
├── server/
│ ├── index.js                              # 服务主入口
│ └── tools/
│ └── domain.js                             # 工具实现
│ └── ip.js                                 # 工具实现
├── .dxtignore                              # 打包排除文件
├── .gitignore
├── icon.svg                                # 智能体图标
├── manifest.json                           # 配置文件
├── package.json                            # Node.js依赖配置
```

### ZoomEye Pro资产管理（python 项目）

**项目示例代码：** 参考 实际案例代码/zoomeye-pro 下的代码。

**项目说明：** ZoomEye Pro资产管理智能体，在使用前，需要先配置 ZoomEye Pro 服务地址、ZoomEye Pro 登录用户名、ZoomEye Pro 登录密码；使用时，可以发起提问“检索192.168.1.11信息”，IP地址替换为需查询的IP。

**项目结构：**

```
zoomeye-pro/
├── .dxtignore
├── .gitignore
├── .python-version         # Python版本（3.12）
├── icon.svg
├── main.py                 # 服务主入口
├── manifest.json           # 配置文件
├── pyproject.toml          # Python依赖配置
```

### Docker配置安全检查（Skills 项目）

**项目示例代码：** 参考 实际案例代码/security-docker 下的代码。

**项目说明：** 识别 Dockerfile、docker-compose.yml 配置中的安全风险。

**项目结构：**

```
security-docker/
├── scripts/                # 存放操作脚本的文件夹
├── manifest.json           # 配置文件
├── SKILL.md                # skill文件
```

## AiPy 自动生成智能体

**操作流程如下：**
在AiPy任务的对话框，输入智能体开发规范所在的文件路径，再输入制作智能体的要求，让AiPy根据《AiPy智能体开发规范-V3.0.md》的要求及相关示例编写智能体。

**提示词示例注意事项：** 
- 告知AiPy存放智能体开发规范文档和相关示例的文件路径
- 说明你需要开发的智能体要求和智能体类型
- 开发完成后，让模型自测，并构建、打包、验证、调试，最后会在工作目录下的项目代码下生成一个智能体文件，直接上传该文件到智能体集市即可使用

**生成智能体的提示词示例：** 以下是一个编写生成周报的智能体的完整示例

```text
文档目录：
- C:\project\git\aigw\tests\functional\others\aipy\AiPy智能体开发规范-V3.0 是存放规范文档和示例文档目录，根据《AiPy智能体开发规范-V3.0.md》的要求及项目示例代码编写一个汇总周报的智能体

智能体编写要求：
- 严格按照《AiPy智能体开发规范-V3.0.md》文档和项目示例代码下的不同类型项目开发智能体
- 智能体版本：企业版

智能体类型：
- 对话工具智能体下的 Prompt 项目

智能体功能要求：
- 根据输入的日报内容汇总周报
- 汇总时不同日期的相同的工作条目合并，根据不同的产品记录不同的项，只记录最终的进度状态
- 输出格式如下，不要生成表格等形式：
  AiPy：
  1.md文档编写 100%
  2.v1.0版本客户端测试 80%
  网关：
  1.跟踪jira缺陷，复测并关闭30个 100%
  2.v1.3.3版本升级包验证 100%

智能体编写完成：
- 严格按照《AiPy智能体开发规范-V3.0.md》文档执行构建、打包、验证、调试流程，查看生成的智能体是否正确、可用
```

# **常见问题排查**

开发过程中常见的几个问题及排查方向：

**问题1：端口输出格式错误**

即使服务已经正常监听，如果 AiPy 没有从标准输出读到端口信息，它也无法接入你的服务。请检查：是否输出到了 STDOUT（不是 STDERR）；输出前是否有其他日志干扰；Python 是否使用了 print(..., flush=True)。详见 4.2 节。

**问题2：tools/list 接口报错**

如果扩展只注册了 Prompt，没有注册任何工具，有时会触发 tools/list 报错。解决办法是同时声明 tools 和 prompts 能力，并额外注册一个空工具 "_"。这属于兼容性处理，详见 4.3 节。

**问题3：dxt pack 打包失败**

很多“本地能跑、安装后不能跑”的问题都来自打包产物不完整。优先检查：入口文件是否真的被打进包里；manifest.json 格式是否正确；.dxtignore 是否误排除了必要文件。详见 4.4 节。

**问题4：智能体调用管理平台模型报错：SSL证书验证失败**

智能体调用管理平台模型，使用https方式访问模型，但管理平台是内网地址，使用自签名证书，导致证书验证失败。智能体使用时需要加一个参数忽略证书验证。web 智能体可通过 `LLM_TLS_REJECT_UNAUTHORIZED` 环境变量控制证书验证，详见 4.5 节「模型调用规范（web 智能体）」。
