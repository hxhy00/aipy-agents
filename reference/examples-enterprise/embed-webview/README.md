# embed-webview 示例项目

这是一个 embed-webview 类型智能体的示例项目，展示如何在 AiPy 对话页内嵌入静态页面。

## 功能说明

本项目实现了一个简单的**待办清单**应用，展示 embed-webview 类型智能体的基本能力：
- 添加新任务
- 标记任务完成/未完成
- 删除任务
- 任务筛选（全部/待处理/已完成）
- 清除已完成任务
- 数据本地存储（localStorage）
- 自动适配亮色/暗色主题

## 项目结构

```
embed-webview/
├── .dxtignore          # 打包排除文件
├── .gitignore          # git排除文件
├── icon.svg            # 智能体图标
├── index.js            # 服务入口源码
├── manifest.json       # 配置文件
├── package.json        # Node.js依赖配置
├── README.md           # 项目说明
└── public/
    └── index.html      # 待办清单页面
```

## 开发要点

### 1. manifest.json 配置
```json
{
  "keywords": ["embed-webview", "其他"]  // 必须包含 embed-webview
}
```

### 2. 服务入口 (index.js)
- 监听端口 0（动态端口分配，避免冲突）
- 输出端口信息到 STDOUT：`{"type": "http_start", "port": 实际端口}`
- 提供 static 文件服务，加载 public 目录下的页面

### 3. 页面要求
- 页面文件放在 `public` 目录下
- 支持根据 URL 参数 `colorScheme` 切换主题：
  - `colorScheme=light` → 亮色主题
  - 其他值（如 `dark`）→ 暗色主题

## 构建打包

```bash
# 安装依赖
bun install

# 构建
bun run build

# 打包
npx @anthropic-ai/dxt pack
```

## 安装使用

将生成的 `embed-webview.dxt` 文件上传到 AiPy 智能体集市即可安装使用。