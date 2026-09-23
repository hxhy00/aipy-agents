"""敏感词检测引擎。

算法层：pyahocorasick（Aho-Corasick 多模式匹配，C 扩展加速，可返回命中位置）。
词库层：
    1. 内置基础词表（BUILTIN_WORDS），覆盖广告法极限词 / 医疗功效 / 金融承诺等
       高风险类别 —— 这些是公众号最常见的违规来源，机器可判。
    2. 外部词库文件（SENSITIVE_WORDLIST 环境变量指向 txt，一行一词），
       加载后与内置词表合并。用于企业自定义词库 / 增量更新。

为什么不用现成的 Python 敏感词包：
    - `sensitive-word`(PyPI 0.5) 实为 `textfilter`，仅提供 filter() 打码，
      不返回命中位置，无法生成带上下文的校验报告；
    - `sensitive-words` 在 PyPI 上不存在；
    - `flashtext` 已停止维护。
    故采用「成熟算法库 pyahocorasick + 自带词库」组合。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import ahocorasick

# ---------- 内置词库 ----------
# 说明：以下为「机器可判定」的高风险类别示例，不含需要人工判断语义的模糊词。
# 公众号实际审核以官方为准，本表用于事前自查，命中即提示人工复核。

BUILTIN_WORDS: dict[str, list[str]] = {
    "广告法-极限词": [
        "国家级", "世界级", "最高级", "最佳", "最好", "最大", "最便宜",
        "第一品牌", "全国第一", "全球第一", "销量第一", "排名第一",
        "绝对", "独一无二", "史无前例", "前所未有", "万能", "100%有效",
        "顶级", "极致", "巅峰", "绝无仅有", "独家秘籍", "唯一",
    ],
    "医疗-功效承诺": [
        "包治百病", "治愈率", "根治", "药到病除", "无副作用", "安全无害",
        "疗效显著", "特效药", "抗癌", "降血压", "降血糖", "壮阳",
    ],
    "金融-收益承诺": [
        "保本保收益", "稳赚不赔", "零风险", "无风险", "高回报", "暴利",
        "一本万利", "躺着赚钱", "日入过万", "月入百万", "包赚",
    ],
    "违禁-导流": [
        "加微信", "加V", "扫码进群", "私信我", "点击链接购买", "免费领取",
        "限时免费", "仅限前", "名额有限速抢",
    ],
}


@dataclass
class Hit:
    word: str
    category: str
    start: int
    end: int


class SensitiveMatcher:
    """基于 Aho-Corasick 的敏感词匹配器。"""

    def __init__(self, words_by_category: dict[str, list[str]] | None = None) -> None:
        self._automaton: ahocorasick.Automaton | None = None
        self._categories: dict[str, str] = {}  # word -> category
        self._build(words_by_category or BUILTIN_WORDS)

    @property
    def word_count(self) -> int:
        return len(self._categories)

    @property
    def categories(self) -> list[str]:
        return sorted(set(self._categories.values()))

    def _build(self, words_by_category: dict[str, list[str]]) -> None:
        auto = ahocorasick.Automaton()
        for category, words in words_by_category.items():
            for w in words:
                w = w.strip()
                if not w:
                    continue
                # 同一词出现在多个类别时，保留先出现的类别
                if w in self._categories:
                    continue
                self._categories[w] = category
                auto.add_word(w, (w, category))
        if len(auto) == 0:
            self._automaton = None
            return
        auto.make_automaton()
        self._automaton = auto

    def match(self, text: str) -> list[Hit]:
        """返回全部命中的敏感词及其位置（按出现顺序）。"""
        if self._automaton is None or not text:
            return []
        hits: list[Hit] = []
        for end_index, (word, category) in self._automaton.iter(text):
            hits.append(
                Hit(
                    word=word,
                    category=category,
                    start=end_index - len(word) + 1,
                    end=end_index + 1,
                )
            )
        return hits


def load_external_wordlist(path: str | None) -> dict[str, list[str]]:
    """加载外部词库 txt（一行一词），与内置词表合并。

    外部词单独归入「自定义词库」类别。
    """
    merged: dict[str, list[str]] = {k: list(v) for k, v in BUILTIN_WORDS.items()}
    if not path:
        return merged
    p = Path(path)
    if not p.is_file():
        return merged
    custom = [
        w.strip()
        for w in p.read_text(encoding="utf-8", errors="ignore").splitlines()
        if w.strip() and not w.strip().startswith("#")
    ]
    if custom:
        merged.setdefault("自定义词库", []).extend(custom)
    return merged


def build_matcher(wordlist_path: str | None = None) -> SensitiveMatcher:
    """按配置构建匹配器。wordlist_path 缺省时读环境变量 SENSITIVE_WORDLIST。"""
    if wordlist_path is None:
        wordlist_path = os.environ.get("SENSITIVE_WORDLIST") or None
    return SensitiveMatcher(load_external_wordlist(wordlist_path))
