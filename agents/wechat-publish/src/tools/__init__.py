"""智能体自带的工具模块：把排版链路上的确定性能力收拢为 MCP 可直接调用的函数。

模块职责一览（均为纯函数，异常一律收敛为 dict 返回，交给 MCP 层转 JSON）：

| 模块              | 对外函数                              | 职责                             |
|-------------------|---------------------------------------|----------------------------------|
| template_style    | extract_template_style                | 模板路径 → 结构化设计参数        |
| html_verify       | verify_html                           | 发布前预检（体积/图片/字段）     |
| verify_fidelity   | verify_fidelity                       | 内容保真 100% 反向核验           |
| minify            | minify_inline_html                    | 内联样式无损压缩                |
| code_image        | render_code_images                    | 代码块 → PNG                     |
| code_image_font   | resolve_code_font                     | 解析可渲染中文的代码字体         |

设计约束（与主工程一致）：
    - 只依赖标准库 + pygments/Pillow（见各模块说明），不引入浏览器；
    - 报错信息面向模型：中文、给出可执行的修复动作，不抛裸异常；
    - 所有路径用 Path 展开，不做硬编码相对路径解析。

注意：本包**不做子模块的 eager 导入**。code_image 依赖 pygments/Pillow，
在未装这两个依赖的环境里 `import src.tools` 仍应可用（其余模块纯标准库），
所以由调用方按需 `from src.tools import code_image`。
"""

from __future__ import annotations

__all__ = [
    "code_image",
    "code_image_font",
    "html_verify",
    "minify",
    "template_style",
    "verify_fidelity",
]

# 子模块名 -> 同名 .py 文件。用 __getattr__ 做惰性导入（PEP 562），
# 既让 `from src.tools import code_image` 可用，又不在包导入时拉起 pygments/Pillow。
_SUBMODULES = frozenset(__all__)


def __getattr__(name: str):
    if name in _SUBMODULES:
        import importlib

        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)