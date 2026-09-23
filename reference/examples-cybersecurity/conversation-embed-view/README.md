# conversation-embed-view 示例项目

这是一个 conversation-embed-view 类型智能体的示例项目，展示如何在 AiPy 对话流中嵌入交互页面。

## 功能说明

本项目实现了一个简单的**信息收集表单**，展示 conversation-embed-view 类型智能体的基本能力：
- 在对话流中嵌入交互页面
- 用户在页面上填写信息
- 提交后将结果返回至对话流继续对话

## 项目结构

```
conversation-embed-view/
├── .dxtignore          # 打包排除文件
├── .gitignore          # git排除文件
├── build.js            # 前端构建脚本
├── icon.svg            # 智能体图标
├── manifest.json       # 配置文件
├── package.json        # Node.js依赖配置
├── README.md           # 项目说明
└── src/
    ├── server/
    │   ├── index.js        # 服务入口
    │   └── handlers/
    │       └── submit-form.js  # 表单提交处理
    └── client/
        ├── index.html      # 页面入口
        ├── index.js        # 前端入口
        └── elements/
            ├── index.js        # 自定义元素注册
            └── form-view.js    # 表单组件
```

## 开发要点

### 1. manifest.json 配置
```json
{
  "keywords": ["conversation-embed-view", "其他"]  // 必须包含 conversation-embed-view
}
```

### 2. 服务入口 (src/server/index.js)
- 监听端口 0（动态端口分配，避免冲突）
- 输出端口信息到 STDOUT：`{"type": "http_start", "port": 实际端口}`
- 提供 API 接口处理用户操作

### 3. 返回结果到对话流
在 handler 中通过 STDOUT 输出标准消息格式：
```javascript
console.log(JSON.stringify({
  type: "client/conversation-embed-view",
  action: "close",
  message: "返回给对话流的消息内容"
}))
```

### 4. 前端页面
- 使用 Web Components (Custom Elements) 构建组件
- 使用 Tailwind CSS 进行样式设计
- 页面自适应容器大小（height: 100vh）

## 构建打包

```bash
# 安装依赖
bun install

# 构建
bun run build

# 打包
bun run pack
```

## 安装使用

将生成的 `conversation-embed-view.dxt` 文件上传到 AiPy 智能体集市即可安装使用。