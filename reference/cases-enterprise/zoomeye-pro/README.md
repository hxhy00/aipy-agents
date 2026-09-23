# ZoomEye Pro MCP 代理插件

连接私有化部署的 ZoomEye Pro实例，将其 MCP 工具透明转发给 AI 助手。

## 配置说明

| 参数 | 说明 | 示例 |
|------|------|------|
| **服务地址** | ZoomEye Pro的访问地址（不含末尾 `/`） | `https://zeye.example.com` |
| **用户名** | 登录账号 | `admin` |
| **密码** | 登录密码 | `••••••••` |

## 工作原理

1. 将上游所有工具（资产查询、任务下发、漏洞探测等）透明暴露给 AI 助手

## 可用工具

连接成功后，工具列表由上游服务器动态决定，通常包含：

- `get_site_list` — 查询资产列表
- `get_site_fields` — 获取资产完整字段
- `create_detection_task` — 下发资产探测任务
- `create_vul_detection_task` — 下发漏洞普查任务
- `create_high_risk_weak_task` — 下发两高一弱检查任务
- `get_task_info` — 查询任务进度
- `get_detection_detail` — 查询探测任务详情
- `get_detection_vul_detail` — 查询漏洞普查详情
- `cancel_task` / `delete_task` — 取消/删除任务
- `get_help` — 使用指南

## 网络要求

运行 AiPy 的机器需能访问 ZoomEye Pro服务地址，支持 HTTP 和 HTTPS（自签名证书）。
