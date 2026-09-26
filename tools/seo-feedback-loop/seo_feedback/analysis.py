from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .db import Database
from .pages import fetch_page_tokens, has_topic_overlap, infer_query_language, page_language


FALLBACK_CTR = {
    "1": 0.28,
    "2": 0.16,
    "3": 0.11,
    "4-5": 0.075,
    "6-10": 0.035,
    "11-20": 0.012,
    "21+": 0.005,
}


def position_bucket(position: float) -> str:
    if position < 1.5:
        return "1"
    if position < 2.5:
        return "2"
    if position < 3.5:
        return "3"
    if position < 5.5:
        return "4-5"
    if position < 10.5:
        return "6-10"
    if position < 20.5:
        return "11-20"
    return "21+"


@dataclass
class QueryMetric:
    query: str
    clicks: float = 0
    impressions: float = 0
    weighted_position: float = 0
    pages: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0

    @property
    def position(self) -> float:
        return self.weighted_position / self.impressions if self.impressions else 0

    @property
    def primary_page(self) -> str:
        return max(self.pages, key=self.pages.get) if self.pages else ""


@dataclass
class Finding:
    query: str
    kind: str
    score: float
    metric: QueryMetric
    previous: QueryMetric | None = None
    expected_ctr: float | None = None
    reason: str = ""


@dataclass
class AnalysisResult:
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date
    total_clicks: float
    total_impressions: float
    previous_clicks: float
    previous_impressions: float
    opportunities: list[Finding]
    declines: list[Finding]
    mismatches: list[Finding]


def _group(rows) -> dict[str, QueryMetric]:
    grouped: dict[str, QueryMetric] = {}
    for row in rows:
        metric = grouped.setdefault(row["query"], QueryMetric(query=row["query"]))
        impressions = float(row["impressions"])
        metric.clicks += float(row["clicks"])
        metric.impressions += impressions
        metric.weighted_position += float(row["position"]) * impressions
        metric.pages[row["page"]] += impressions
    return grouped


def _ctr_curve(database: Database, end_day: date) -> dict[str, float]:
    rows = database.ctr_baseline(end_day - timedelta(days=89), end_day)
    observed = {row["position_bucket"]: row for row in rows}
    curve = {}
    for bucket, fallback in FALLBACK_CTR.items():
        row = observed.get(bucket)
        if not row or float(row["impressions"]) <= 0:
            curve[bucket] = fallback
            continue
        impressions = float(row["impressions"])
        empirical = float(row["clicks"]) / impressions
        weight = min(1.0, impressions / 200.0)
        curve[bucket] = (empirical * weight) + (fallback * (1 - weight))
    return curve


def _percent_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return (current - previous) / previous


def analyze(database: Database, min_impressions: int = 10) -> AnalysisResult:
    latest = database.latest_day()
    if latest is None:
        raise RuntimeError("No Search Console data has been collected yet.")
    current_end = latest
    current_start = current_end - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    current = _group(database.aggregate(current_start, current_end))
    previous = _group(database.aggregate(previous_start, previous_end))
    ctr_curve = _ctr_curve(database, current_end)

    opportunities: list[Finding] = []
    declines: list[Finding] = []
    mismatches: list[Finding] = []
    page_cache: dict[str, set[str] | None] = {}

    for query, metric in current.items():
        if metric.impressions < min_impressions:
            continue
        prior = previous.get(query)
        expected = ctr_curve[position_bucket(metric.position)]
        ctr_ratio = metric.ctr / expected if expected else 1
        if 3 <= metric.position <= 20:
            score = 3 + min(3, math.log10(metric.impressions + 1))
            if ctr_ratio < 0.7:
                score += min(3, (0.7 - ctr_ratio) * 4)
            opportunities.append(
                Finding(query, "opportunity", score, metric, prior, expected)
            )

        if prior and prior.impressions >= min_impressions:
            click_change = _percent_change(metric.clicks, prior.clicks)
            impression_change = _percent_change(metric.impressions, prior.impressions)
            position_loss = metric.position - prior.position
            reasons = []
            severity = 0.0
            if click_change is not None and click_change <= -0.30 and prior.clicks >= 3:
                reasons.append(f"clicks {click_change:.0%}")
                severity += abs(click_change) * 4
            if impression_change is not None and impression_change <= -0.35:
                reasons.append(f"impressions {impression_change:.0%}")
                severity += abs(impression_change) * 3
            if position_loss >= 2:
                reasons.append(f"position +{position_loss:.1f}")
                severity += min(4, position_loss / 2)
            if reasons:
                declines.append(
                    Finding(query, "decline", severity, metric, prior, expected, ", ".join(reasons))
                )

        page = metric.primary_page
        inferred = infer_query_language(query)
        mismatch_reasons = []
        if inferred and inferred != page_language(page):
            mismatch_reasons.append(f"query language {inferred}, page {page_language(page)}")
        if page:
            if page not in page_cache:
                try:
                    page_cache[page] = fetch_page_tokens(page)
                except Exception:
                    page_cache[page] = None
            page_words = page_cache[page]
            if page_words is not None and not has_topic_overlap(query, page_words):
                mismatch_reasons.append("query topic is absent from visible page text")
        if mismatch_reasons:
            mismatches.append(
                Finding(
                    query,
                    "mismatch",
                    2 + min(3, math.log10(metric.impressions + 1)),
                    metric,
                    prior,
                    expected,
                    "; ".join(mismatch_reasons),
                )
            )

    opportunities.sort(key=lambda item: item.score, reverse=True)
    declines.sort(key=lambda item: item.score, reverse=True)
    mismatches.sort(key=lambda item: item.score, reverse=True)
    return AnalysisResult(
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=previous_end,
        total_clicks=sum(item.clicks for item in current.values()),
        total_impressions=sum(item.impressions for item in current.values()),
        previous_clicks=sum(item.clicks for item in previous.values()),
        previous_impressions=sum(item.impressions for item in previous.values()),
        opportunities=opportunities,
        declines=declines,
        mismatches=mismatches,
    )
