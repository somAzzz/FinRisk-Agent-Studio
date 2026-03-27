"""Tier detection logic for search tool routing (低成本规则引擎).

Determines whether a query should use:
- ddgs: Simple fact queries, stock tickers, official websites
- tavily: Deep analysis, multi-source news, trend research
- None: Let LLM router decide (ambiguous cases)
"""

import re
from typing import Literal

# 深度搜索关键词（触发 Tavily）
_DEEP_SEARCH_KEYWORDS = {
    # 分析/总结类
    "分析", "分析报告", "总结", "趋势",
    "analysis", "analyze", "summary", "trend",
    # 新闻类
    "新闻", "latest", "recent", "recently", "new",
    # 多源/全面类
    "multi-source", "comprehensive", "多源", "全面", "深度",
    "multi source", "all about",
    # 财报/业绩类
    "earnings", "财报", "业绩", "forecast", "outlook",
    "quarterly", "annual", "revenue", "profit",
    # 对比类
    "vs", "versus", "compare", "对比", "比较",
    # 预测/展望类
    "预测", "展望", "projection",
}

# 简单查询关键词（触发 ddgs）
_SIMPLE_QUERY_KEYWORDS = {
    # 股票代码类
    "股票代码", "stock ticker", "ticker", "股票号",
    # 官方网站类
    "官方网站", "official website", "官网", "homepage",
    # 事实核查类
    "fact-check", "验证", "是不是", "是否", "真伪",
    "is it true", "verify", "true or false",
    # 快速定义类
    "什么是", "what is", "who is", "定义",
    # 当前价格类
    "当前价格", "now price", "current price",
    # 简单评价类
    "good stock", "is a good",
}

# 金融实体 + 多源组合 → tavily
_FINANCIAL_ENTITY_MULTI = {
    "stock", "stocks", "share", "shares", "equity", "equities",
    "bond", "bonds", "etf", "index",
}


def detect_search_tier(query: str) -> Literal["ddgs", "tavily", None]:
    """Detect which search tier a query should use.

    Returns:
        "ddgs" — Simple query pattern matched
        "tavily" — Deep search pattern matched
        None — Ambiguous, let LLM decide
    """
    query_lower = query.lower()

    # 检查简单查询关键词
    if any(kw in query_lower for kw in _SIMPLE_QUERY_KEYWORDS):
        return "ddgs"

    # 检查深度搜索关键词
    if any(kw in query_lower for kw in _DEEP_SEARCH_KEYWORDS):
        return "tavily"

    # 金融实体 + 多源需求 → tavily
    has_financial_entity = any(ent in query_lower for ent in _FINANCIAL_ENTITY_MULTI)
    has_multi_marker = any(kw in query_lower for kw in {"compare", "对比", "multiple", "多", "all"})
    if has_financial_entity and has_multi_marker:
        return "tavily"

    # 默认让 LLM 决定
    return None


def is_direct_url(text: str) -> bool:
    """Detect if input is a direct URL."""
    return bool(re.match(r"^https?://", text.strip()))