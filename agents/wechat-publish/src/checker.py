"""check_text 文字层校验：标点规范、品牌名、敏感词。

依据《公众号发布全流程规范手册_v2.3》第四/五部分转成自动规则。
视觉层问题（封面裁切、图片溢出、空行错乱）无法机器检查，
报告中统一标注「需人工手机端预览确认」。

敏感词检测由 src/sensitive.py 提供（pyahocorasick + 内置/外部词库）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

from .sensitive import build_matcher

# ---------- 规则定义 ----------

@dataclass
class Issue:
    rule: str       # 规则标识
    severity: str   # error / warning
    text: str       # 命中原文
    context: str    # 上下文片段
    suggestion: str # 修改建议


@dataclass
class CheckReport:
    issues: list[Issue] = field(default_factory=list)

    def add(self, **kwargs) -> None:
        self.issues.append(Issue(**kwargs))

    def summary(self) -> str:
        if not self.issues:
            return "校验通过：未发现文字层问题。"
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = len(self.issues) - errors
        lines = [f"共发现 {len(self.issues)} 个问题（{errors} 个 error / {warnings} 个 warning）："]
        for i, iss in enumerate(self.issues, 1):
            lines.append(
                f"{i}. [{iss.severity.upper()}] {iss.rule}："
                f"「{iss.text}」→ {iss.suggestion}（上下文：…{iss.context}…）"
            )
        lines.append("")
        lines.append("注：封面裁切、图片溢出、空行/折行等视觉问题无法自动检查，需人工手机端预览确认。")
        return "\n".join(lines)


BRAND_CORRECT = "AiPY"
# 品牌名错误写法：aipy / Aipy / aIPy / AIPY 等
BRAND_PATTERN = re.compile(r"(?<![A-Za-z])[Aa][Ii][Pp][Yy](?![A-Za-z])")

# 常见中英混排标点问题
HALF_TO_FULL = {
    ",": "，",
    ";": "；",
    "?": "？",
    "!": "！",
}
SENTENCE_END = re.compile(r"[\u4e00-\u9fff](,|;|\?|!)(?=\s|$|[\u4e00-\u9fff])")
# 中文语境里的直引号
STRAIGHT_QUOTES = re.compile(r'("[^"\u201c\u201d]{1,40}")')

# 敏感词匹配器：进程内单例，避免每次调用重建 AC 自动机
_MATCHER = None


def _get_matcher():
    global _MATCHER
    if _MATCHER is None:
        _MATCHER = build_matcher(os.environ.get("SENSITIVE_WORDLIST") or None)
    return _MATCHER


def _context_of(text: str, start: int, end: int, width: int = 15) -> str:
    return text[max(0, start - width):min(len(text), end + width)]


def _check_punctuation(text: str, report: CheckReport) -> None:
    for m in SENTENCE_END.finditer(text):
        ch = m.group(1)
        report.add(
            rule="标点-半角符号",
            severity="warning",
            text=ch,
            context=_context_of(text, m.start(), m.end()),
            suggestion=f"中文语境应使用全角符号「{HALF_TO_FULL[ch]}」",
        )
    for m in STRAIGHT_QUOTES.finditer(text):
        report.add(
            rule="标点-直引号",
            severity="warning",
            text=m.group(1),
            context=_context_of(text, m.start(), m.end()),
            suggestion="中文语境应使用弯引号「“”」",
        )


def _check_brand(text: str, report: CheckReport) -> None:
    for m in BRAND_PATTERN.finditer(text):
        if m.group(0) != BRAND_CORRECT:
            report.add(
                rule="品牌名",
                severity="error",
                text=m.group(0),
                context=_context_of(text, m.start(), m.end()),
                suggestion=f"品牌名应统一写作「{BRAND_CORRECT}」",
            )


def _check_sensitive(text: str, report: CheckReport) -> None:
    """用 Aho-Corasick 匹配内置 + 外部词库，输出命中类别与位置。"""
    matcher = _get_matcher()
    seen: set[tuple[str, int]] = set()
    for hit in matcher.match(text):
        key = (hit.word, hit.start)
        if key in seen:
            continue
        seen.add(key)
        report.add(
            rule=f"敏感词-{hit.category}",
            severity="error",
            text=hit.word,
            context=_context_of(text, hit.start, hit.end),
            suggestion="命中敏感词库，请复核或改写（词库见 SENSITIVE_WORDLIST 配置）",
        )


def sensitive_wordlist_stats() -> str:
    """返回当前装载的词库统计，供工具自检/排查。"""
    m = _get_matcher()
    return f"已装载 {m.word_count} 个敏感词，类别：{'、'.join(m.categories)}"


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def check_text(html_or_text: str) -> CheckReport:
    """对 HTML 或纯文本执行文字层校验。"""
    if "<" in html_or_text and ">" in html_or_text:
        text = extract_text_from_html(html_or_text)
    else:
        text = html_or_text

    report = CheckReport()
    _check_punctuation(text, report)
    _check_brand(text, report)
    _check_sensitive(text, report)
    return report
