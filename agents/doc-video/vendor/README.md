# vendor/ — 内置 ffmpeg / ffprobe 二进制

本目录存放各平台的 `ffmpeg` / `ffprobe` 二进制，**随扩展包（.mcpb）整体分发**，
供渲染服务端在用户本机直接调用，用户无需自行安装 ffmpeg。

## 三平台目录名约定

| 目录 | 平台 | 内容 |
|------|------|------|
| `darwin-arm64/` | macOS（Apple Silicon） | `ffmpeg`、`ffprobe`（原始二进制） |
| `darwin-x64/` | macOS（Intel） | `ffmpeg`、`ffprobe`（原始二进制） |
| `win32-x64/` | Windows x64 | `ffmpeg.exe.gz`、`ffprobe.exe.gz`（gzip 压缩存放） |

- 二进制由 `scripts/fetch-ffmpeg.sh` 获取后按上述目录名归位。
- Windows 侧以 `.gz` 压缩存放，首次调用时由 `server/lib/binaries.js` 惰性解压到 `~/.aipy/bin`。

## 为什么二进制不进版本库（git）

1. **体积过大**：三平台全量约 294MB，进版本库会让仓库克隆与日常拉取都变得不可接受。
2. **GitHub 单文件 100MB 硬限制**：`darwin-x64/ffprobe`（约 79MB）等文件已逼近上限，更大的文件会被直接拒收。
3. **按平台按需获取**：持续集成（CI）与打包时只需下载目标平台对应的一个子目录，无需全量持有三平台二进制。

## 注意事项

- **本目录整体必须随包分发**：`.mcpbignore` 中不要加入任何针对 `/vendor/` 的忽略规则。
- 各平台子目录下的 `.gitkeep` 仅用于让 git 保留空目录结构，体积可忽略，不影响打包。
