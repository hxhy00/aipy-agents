# vendor/ — 可选的 ffmpeg / ffprobe 本地内置目录

## 结论先讲：发布包不内置 ffmpeg

发布到 GitHub Release 的 `doc-video.mcpb` **不含 ffmpeg 二进制**，用户需自行安装：

- macOS：`brew install ffmpeg`
- Windows：`winget install Gyan.FFmpeg`

原因见下一节。插件代码已按「系统 ffmpeg 优先」设计，`server/lib/binaries.js`
会自动在系统 PATH 与常见安装路径（`/opt/homebrew/bin`、`C:\Program Files\ffmpeg\bin`、
winget / scoop / chocolatey 落地位置等）中查找，用户装完即可用，无需改配置。

## 为什么不再内置

1. **超过 GitHub Release 单文件 100MB 硬限制**：三平台全量 ffmpeg 约 126MB，
   打包后的 `.mcpb` 约 140MB，push 到 Release 会被直接拒绝。
2. **仓库无法持有**：三平台原始二进制约 294MB，其中 `darwin-x64/ffprobe` 单文件约 79MB，
   已逼近 git 的硬上限，克隆与拉取成本不可接受。
3. **多平台包只能分包**：要内置就得按平台出多个包，安装时容易选错，收益不抵复杂度。
4. **安装成本低**：Homebrew / winget 都是用户机器上的成熟方案，一条命令解决。

## 本目录还有什么用

保留该目录与查找逻辑，是为了**本地开发与调试**：

- `scripts/fetch-ffmpeg.sh` 可把二进制拉到对应平台子目录（见下），
  打包时会随包携带、`binaries.js` 会自动优先命中，便于离线验证内置链路。
- 若将来改为「按平台分包分发」，只需重新把 `vendor/` 纳入 `.mcpbignore` 白名单即可，代码无需改动。

## 目录名约定（与 `binaries.js` 的 `platformTag()` 一致）

| 目录 | 平台 | 内容 |
|------|------|------|
| `darwin-arm64/` | macOS（Apple Silicon） | `ffmpeg`、`ffprobe`（原始二进制） |
| `darwin-x64/` | macOS（Intel） | `ffmpeg`、`ffprobe`（原始二进制） |
| `win32-x64/` | Windows x64 | `ffmpeg.exe.gz`、`ffprobe.exe.gz`（gzip 压缩存放） |

- 获取方式：`./scripts/fetch-ffmpeg.sh`（自动识别当前平台）、
  `./scripts/fetch-ffmpeg.sh darwin-arm64`（指定平台）、`all`（三平台全量）。
- Windows 侧以 `.gz` 压缩存放，首次调用时由 `server/lib/binaries.js` 惰性解压到 `~/.aipy/bin`。
- 各子目录下的 `.gitkeep` 仅用于让 git 保留空目录结构。

## 当前状态

- `.mcpbignore` 中 `/vendor/` 已加入忽略列表，**不会随发布包分发**；
  与上面的「本地开发可携带」并不冲突——发版时忽略，本地调试时可临时移除该行。
