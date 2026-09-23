#!/usr/bin/env bash
#
# 获取 ffmpeg / ffprobe 二进制并按平台归位到 agents/doc-video/vendor/。
#
# 为什么需要这个脚本：
#   发布包不内置 ffmpeg（三平台全量约 126MB，打包后会超过 GitHub Release
#   单文件 100MB 硬限制），用户改为自行安装；本脚本供本地开发时拉取二进制，
#   用于验证「内置二进制」这条解析链路，也可在将来改回内置分发时直接复用。
#
# 用法：
#   ./scripts/fetch-ffmpeg.sh                    # 自动识别当前平台
#   ./scripts/fetch-ffmpeg.sh darwin-arm64       # 指定单一平台
#   ./scripts/fetch-ffmpeg.sh all                # 三平台全量（约 126MB）
#
# 输出目录：agents/doc-video/vendor/<platform>/
#   darwin-arm64/  ffmpeg, ffprobe          （原始二进制，含可执行位）
#   darwin-x64/    ffmpeg, ffprobe          （原始二进制，含可执行位）
#   win32-x64/     ffmpeg.exe.gz, ffprobe.exe.gz （gzip 存放，运行时惰性解压）
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/agents/doc-video/vendor"

# ---------- 下载源 ----------
# macOS 双架构走 martin-riedl.de 的静态构建（已实测 200）。
# 注意：evermeet.cx 只提供 Intel(amd64) 构建，arm64 请勿使用。
MACOS_BASE="https://ffmpeg.martin-riedl.de/redirect/latest/macos"
# Windows 走 BtbN 的 GitHub Release（essentials 构建，含 ffmpeg + ffprobe）
WIN_ZIP_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

log()  { printf '\033[1;34m[fetch-ffmpeg]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[fetch-ffmpeg]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[fetch-ffmpeg]\033[0m %s\n' "$*" >&2; exit 1; }

need() {
	command -v "$1" >/dev/null 2>&1 || die "缺少依赖命令：$1"
}

# 检测本机平台标签，与 server/lib/binaries.js 的 platformTag() 保持一致
detect_platform() {
	case "$(uname -s)" in
		Darwin) echo "darwin-$( [ "$(uname -m)" = "arm64" ] && echo arm64 || echo x64 )" ;;
		Linux)  echo "linux-$( [ "$(uname -m)" = "aarch64" ] && echo arm64 || echo x64 )" ;;
		MINGW*|MSYS*|CYGWIN*|Windows_NT) echo "win32-x64" ;;
		*) die "无法识别的平台：$(uname -s)" ;;
	esac
}

# ---------- macOS：下载 zip 解包，取出 ffmpeg / ffprobe ----------
fetch_macos() {
	local tag="$1" arch dest tmp
	case "$tag" in
		darwin-arm64) arch="arm64" ;;
		darwin-x64)   arch="amd64" ;;
		*) die "不支持的 macOS 平台标签：$tag" ;;
	esac

	dest="${VENDOR_DIR}/${tag}"
	mkdir -p "$dest"
	tmp="$(mktemp -d)"
	trap 'rm -rf "$tmp"' RETURN

	for bin in ffmpeg ffprobe; do
		local url="${MACOS_BASE}/${arch}/release/${bin}.zip"
		log "[$tag] 下载 ${bin} ← ${url}"
		curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 -o "${tmp}/${bin}.zip" "$url" \
			|| die "[$tag] 下载 ${bin} 失败"

		# 压缩包内通常只有同名二进制，直接解出
		unzip -q -o "${tmp}/${bin}.zip" -d "${tmp}/${bin}" || die "[$tag] 解压 ${bin} 失败"
		local found
		found="$(find "${tmp}/${bin}" -type f -name "$bin" -perm -u+x -o -type f -name "$bin" | head -1)"
		[ -n "$found" ] || die "[$tag] 解压后未找到 ${bin}"
		install -m 0755 "$found" "${dest}/${bin}"
		log "[$tag] ${bin} → ${dest}/${bin}（$(du -h "${dest}/${bin}" | cut -f1)）"
	done
}

# ---------- Windows：下载 zip，取 exe 后 gzip 存放 ----------
fetch_win() {
	local tag="win32-x64" dest tmp
	dest="${VENDOR_DIR}/${tag}"
	mkdir -p "$dest"
	tmp="$(mktemp -d)"
	trap 'rm -rf "$tmp"' RETURN

	log "[$tag] 下载 ffmpeg+ffprobe ← ${WIN_ZIP_URL}"
	curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 15 -o "${tmp}/win.zip" "$WIN_ZIP_URL" \
		|| die "[$tag] 下载失败"

	unzip -q -o "${tmp}/win.zip" -d "${tmp}/x" || die "[$tag] 解压失败"

	for bin in ffmpeg ffprobe; do
		local found
		found="$(find "${tmp}/x" -type f -name "${bin}.exe" | head -1)"
		[ -n "$found" ] || die "[$tag] 未找到 ${bin}.exe"
		# .gz 存放：运行时由 server/lib/binaries.js 惰性解压，可让包体积减半
		gzip -9 -c "$found" > "${dest}/${bin}.exe.gz"
		log "[$tag] ${bin}.exe.gz → ${dest}/${bin}.exe.gz（$(du -h "${dest}/${bin}.exe.gz" | cut -f1)）"
	done
}

need curl
need unzip

TARGETS=()
case "${1:-auto}" in
	auto) TARGETS=("$(detect_platform)") ;;
	all)  TARGETS=(darwin-arm64 darwin-x64 win32-x64) ;;
	darwin-arm64|darwin-x64|win32-x64) TARGETS=("$1") ;;
	linux-x64|linux-arm64)
		# 发布包不内置 ffmpeg，Linux 用户直接用包管理器安装即可，无需本脚本
		warn "脚本目前只获取 macOS 与 Windows 二进制（与 vendor/ 下的三个平台子目录对应）。"
		warn "Linux 用户请直接用系统包管理器安装 ffmpeg（apt/dnf/pacman），插件会自动在 PATH 中找到。"
		exit 0
		;;
	*) die "未知参数：$1（可用：auto | all | darwin-arm64 | darwin-x64 | win32-x64）" ;;
esac

log "目标平台：${TARGETS[*]}"
for t in "${TARGETS[@]}"; do
	case "$t" in
		darwin-*) fetch_macos "$t" ;;
		win32-*)  fetch_win ;;
	esac
done

log "完成。校验结果："
find "$VENDOR_DIR" -type f ! -name '.gitkeep' ! -name 'README.md' -exec ls -lh {} \; | awk '{print "  " $9 "  " $5}'
