"""智能体内置资源（SOP / 参考规范 / 视觉素材）的读取层。

为什么需要这个模块
------------------
排版能力的「知识层」（流程规则、风格矩阵、视觉素材）随包打进 resources/，
但智能体是装在用户机器上跑的，模型既拿不准包被解压到哪个目录，也不该用 shell
去翻目录——既不可移植，也没有任何白名单约束。

这里把资源读取收敛成 3 个纯函数（read_sop / read_reference / read_asset），
由 main.py 注册为 get_sop / get_reference / get_asset 三个 MCP 工具。

安全边界（本模块唯一的硬约束）
------------------------------
所有外部输入的路径参数都**不参与路径拼接**，只能命中白名单：

    reference 名 → 白名单 = resources/references/ 下实际存在的 .md 文件名
    asset 类目   → 白名单 = resources/assets/ 下的子目录名
    asset 文件名 → 白名单 = 该类目目录下实际存在的文件名

白名单一律用 Path.iterdir() **动态枚举**，不硬编码清单：
以后往包里加参考文档或素材，工具自动可用，不会出现「加了文件但工具读不到」
这种必须同步改两处的隐性坑。

路径穿越防护是双层的，缺一层都不行：

    第 1 层（_reject_traversal）：字符串级拦截。含 / \\ .. 、绝对路径或 ~ 开头的
        输入直接拒绝，并把错误信息讲成「只能传文件名，不能传路径」——
        模型读到这句话就会自己纠正，不需要额外一轮试错。
    第 2 层（_assert_inside）：真正读文件前复核 resolve() 结果仍在基准目录内。
        只做第 1 层会在「白名单文件本身是软链接」时漏口；只做第 2 层则错误信息
        会泄露包外目录结构。

依赖：仅标准库（本模块随 server 主进程启动，绝不能引入任何第三方依赖，
否则缺依赖会连累全部 13 个工具都起不来）。
"""

from __future__ import annotations

import re
from pathlib import Path

# 单个资源文件的读取上限。素材与规范文档都在几十 KB 量级，
# 设上限是为了防止将来误打包进大文件时把模型上下文一次性打爆。
_MAX_BYTES = 512 * 1024

# 允许按文本读取的资产后缀。assets/ 下目前只有 .html/.svg/.json 三类，
# 这里多留几个同类后缀，避免以后加 .css/.md 素材时要改代码。
_TEXT_SUFFIXES = {
    ".html", ".htm", ".svg", ".json", ".css", ".js",
    ".md", ".txt", ".xml", ".yaml", ".yml",
}

# 章节切分只认二级/三级标题。一级标题是文档名（"# AI 公众号视觉设计师"），
# 拿它当章节没有意义，会让 section 匹配结果变得含糊。
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)


# ---------- 基础工具 ----------


def _resources_root() -> Path:
    """定位打包内的 resources/ 目录。

    用 __file__ 绝对化而不是相对路径：CWD 由宿主（AiPy 客户端拉起的子进程）
    决定，不保证是包目录，只有 __file__ 是可靠的。
    """
    return Path(__file__).resolve().parent.parent / "resources"


def _norm(value: str) -> str:
    """标题/查询词归一化：去全部空白 + 转小写，让「步骤 4」「步骤4」都能命中。"""
    return re.sub(r"\s+", "", value.strip().lower())


def _reject_traversal(value: str, field: str) -> str:
    """校验一个「只能是文件名」的输入，返回去空白后的值；不合法直接抛 ValueError。

    白名单语义下，合法名字不可能含分隔符或 ..，所以这里不需要、也不应该
    做任何「先拼接再校验」式的路径解析——那正是路径穿越漏洞的经典成因。
    """
    v = (value or "").strip()
    if not v:
        raise ValueError(f"{field} 不能为空")
    if any(ch in v for ch in ("/", "\\", "\x00")) or ".." in v:
        raise ValueError(
            f"{field} 只能是文件名，不能传路径：{value!r}。"
            "本工具的每个参数都对应一个内置资源名，不接受目录、相对路径或 ../ 穿越。"
        )
    if v.startswith("~") or Path(v).is_absolute():
        raise ValueError(f"{field} 不能是绝对路径或 ~ 开头的路径：{value!r}，只能传文件名")
    return v


def _assert_inside(path: Path, base: Path) -> Path:
    """复核 resolve() 后 path 仍在 base 目录内，否则抛 ValueError。

    resolve() 会展开软链接，所以白名单文件被换成指向包外的软链接时能被拦住。
    """
    resolved = path.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError("越界访问被拒绝：目标不在允许的资源目录内")
    return resolved


def _read_text(path: Path) -> str:
    """按 UTF-8 读取资源文本，超过上限直接拒绝。"""
    size = path.stat().st_size
    if size > _MAX_BYTES:
        raise ValueError(
            f"资源文件过大（{size // 1024}KB > {_MAX_BYTES // 1024}KB）：{path.name}，"
            "请改用更精确的章节/类目查询，不要整份读入。"
        )
    return path.read_text(encoding="utf-8")


def _ok(**fields: object) -> dict:
    """统一的成功返回骨架，保证模型侧按固定 schema 解析。"""
    return {"ok": True, **fields}


def _fail(error: str, **extra: object) -> dict:
    """统一的失败返回骨架。"""
    return {"ok": False, "error": error, **extra}


# ---------- SOP ----------


def _split_sections(text: str) -> list[tuple[str, str]]:
    """按 Markdown 二级/三级标题把 SOP.md 切成若干章节。

    返回 [(标题, 该章节正文（含标题行))]，顺序与文档一致。
    第一个 ## 之前的引言部分（文档名、能力唤起描述原文、读取方式说明）
    不归属任何章节——需要它时用不带 section 的 get_sop 取全文。
    """
    marks = list(_HEADING_RE.finditer(text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(marks):
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(2).strip(), text[start:end].rstrip() + "\n"))
    return out


def list_sections() -> list[str]:
    """列出 SOP.md 的全部章节名（章节查询失败时回给模型，避免它反复猜名字）。"""
    sop = _resources_root() / "SOP.md"
    if not sop.is_file():
        return []
    return [title for title, _ in _split_sections(sop.read_text(encoding="utf-8"))]


def read_sop(section: str = "") -> dict:
    """读取排版全流程 SOP 全文或某一章节。

    参数：
        section: 章节名或关键词，留空返回全文。

    返回 {ok, section, content, chars, available_sections}；
    匹配不到时 ok=false 并回带完整可用章节名列表。
    """
    sop = _resources_root() / "SOP.md"
    if not sop.is_file():
        return _fail(f"内置 SOP 文件缺失：{sop}")

    try:
        text = sop.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return _fail(f"读取 SOP 失败：{type(e).__name__}: {e}")

    sections = _split_sections(text)
    titles = [title for title, _ in sections]
    wanted = (section or "").strip()

    if not wanted:
        return _ok(
            section="",
            content=text,
            chars=len(text),
            available_sections=titles,
            hint='需要局部内容时用 get_sop(section="章节名") 取一段，例如 section="步骤 4"。',
        )

    key = _norm(wanted)

    # 先精确匹配，避免「全流程约束」被「约束」之类的模糊命中抢走。
    for title, body in sections:
        if _norm(title) == key:
            return _ok(section=title, content=body, chars=len(body), available_sections=titles)

    # 再做双向包含匹配；多个命中时不猜，把候选交给模型选。
    hits = [(t, b) for t, b in sections if key in _norm(t) or _norm(t) in key]
    if len(hits) == 1:
        title, body = hits[0]
        return _ok(section=title, content=body, chars=len(body), available_sections=titles)
    if len(hits) > 1:
        return _fail(
            f"章节名「{wanted}」匹配到多个章节，请指定更完整的名称。",
            candidates=[t for t, _ in hits],
            available_sections=titles,
        )

    return _fail(
        f"没有名为「{wanted}」的章节。可用章节名如下，请直接照抄其中一个：",
        available_sections=titles,
    )


# ---------- references ----------


def _reference_names() -> list[str]:
    """references/ 下实际存在的 .md 文件名（不含后缀），动态枚举。"""
    d = _resources_root() / "references"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".md")


def read_reference(name: str) -> dict:
    """读取一篇排版规范文档（references 下的 Markdown）。

    name 走白名单：只接受 references/ 下实际存在的 .md 文件名，
    带不带 .md 后缀都接受（模型两种写法都会出现）。
    """
    available = _reference_names()
    try:
        wanted = _reject_traversal(name, "name")
    except ValueError as e:
        return _fail(str(e), available_references=available)

    if not available:
        return _fail("内置 references 目录缺失或为空，无法读取参考规范。")

    stem = wanted[:-3] if wanted.lower().endswith(".md") else wanted
    if stem not in available:
        return _fail(
            f"没有名为「{name}」的参考规范。可用文件名如下，请直接照抄其中一个：",
            available_references=available,
        )

    base = _resources_root() / "references"
    try:
        path = _assert_inside(base / f"{stem}.md", base)
        content = _read_text(path)
    except (ValueError, OSError, UnicodeDecodeError) as e:
        return _fail(f"读取参考规范「{stem}」失败：{e}", available_references=available)

    return _ok(name=stem, content=content, chars=len(content), available_references=available)


# ---------- assets ----------


def _asset_categories() -> list[str]:
    """assets/ 下的子目录名，动态枚举。"""
    d = _resources_root() / "assets"
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def _asset_files(category_dir: Path) -> list[str]:
    return sorted(p.name for p in category_dir.iterdir() if p.is_file())


def read_asset(category: str, name: str = "") -> dict:
    """读取视觉素材库里的一类素材。

    参数：
        category: 类目目录名，走白名单（assets/ 下实际存在的子目录）。
        name:     类目下的文件名；留空时返回该类目的文件清单。

    assets/ 下的素材都是文本（.html/.svg/.json），统一按 UTF-8 读出源码，
    由模型自行内联到排版产物里。
    """
    available = _asset_categories()
    try:
        wanted_cat = _reject_traversal(category, "category")
    except ValueError as e:
        return _fail(str(e), available_categories=available)

    if not available:
        return _fail("内置 assets 目录缺失或为空，无法读取视觉素材。")

    if wanted_cat not in available:
        return _fail(
            f"没有名为「{category}」的素材类目。可用类目如下，请直接照抄其中一个：",
            available_categories=available,
        )

    root = _resources_root() / "assets"
    try:
        cat_dir = _assert_inside(root / wanted_cat, root)
        files = _asset_files(cat_dir)
    except (ValueError, OSError) as e:
        return _fail(f"读取素材类目「{wanted_cat}」失败：{e}", available_categories=available)

    wanted_name = (name or "").strip()
    if not wanted_name:
        return _ok(
            category=wanted_cat,
            name="",
            files=files,
            hint='需要具体素材时用 get_asset(category="%s", name="文件名") 取源码。' % wanted_cat,
        )

    try:
        wanted_name = _reject_traversal(wanted_name, "name")
    except ValueError as e:
        return _fail(str(e), category=wanted_cat, files=files)

    if wanted_name not in files:
        return _fail(
            f"类目「{wanted_cat}」下没有名为「{name}」的素材。可用文件如下：",
            category=wanted_cat,
            files=files,
        )

    try:
        path = _assert_inside(cat_dir / wanted_name, cat_dir)
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            return _fail(
                f"素材「{wanted_name}」不是可读文本文件（仅支持 {sorted(_TEXT_SUFFIXES)}）。",
                category=wanted_cat,
                files=files,
            )
        content = _read_text(path)
    except (ValueError, OSError, UnicodeDecodeError) as e:
        return _fail(f"读取素材「{wanted_cat}/{wanted_name}」失败：{e}", category=wanted_cat, files=files)

    return _ok(
        category=wanted_cat,
        name=wanted_name,
        content=content,
        chars=len(content),
        files=files,
        hint="取到的是源码片段，占位文字必须替换为本篇原文；不适用就不使用该组件。",
    )
