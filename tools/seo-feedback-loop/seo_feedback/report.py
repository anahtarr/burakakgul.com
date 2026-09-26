from __future__ import annotations

from .analysis import AnalysisResult, Finding


def _pct(current: float, previous: float) -> str:
    if previous <= 0:
        return "new" if current > 0 else "0%"
    change = (current - previous) / previous
    return f"{change:+.0%}"


def _metric_line(finding: Finding) -> str:
    metric = finding.metric
    expected = ""
    if finding.expected_ctr is not None:
        expected = f" · expected {finding.expected_ctr:.1%}"
    return (
        f"“{finding.query}”\n"
        f"Position {metric.position:.1f} · {metric.impressions:.0f} impressions · "
        f"CTR {metric.ctr:.1%}{expected}"
    )


def render(result: AnalysisResult, top_n: int = 3) -> str:
    lines = [
        "📈 burakakgul.com — Weekly SEO",
        f"📅 {result.current_start.isoformat()} → {result.current_end.isoformat()}",
        "",
        f"Clicks: {result.total_clicks:.0f} ({_pct(result.total_clicks, result.previous_clicks)})",
        f"Impressions: {result.total_impressions:.0f} ({_pct(result.total_impressions, result.previous_impressions)})",
    ]
    if result.opportunities:
        lines.extend(["", "🎯 OPPORTUNITIES"])
        for finding in result.opportunities[:top_n]:
            lines.extend([_metric_line(finding), "Action: review title, description and matching on the existing page."])
    if result.declines:
        lines.extend(["", "⚠️ DECLINES"])
        for finding in result.declines[:top_n]:
            lines.extend([_metric_line(finding), f"Change: {finding.reason}."])
    if result.mismatches:
        lines.extend(["", "🧩 POSSIBLE QUERY/PAGE MISMATCH"])
        for finding in result.mismatches[:top_n]:
            lines.extend([_metric_line(finding), f"Reason: {finding.reason}."])
    if not (result.opportunities or result.declines or result.mismatches):
        lines.extend(["", "✅ No meaningful action signal this week."])
    lines.extend(["", "No automatic site changes were made."])
    return "\n".join(lines)[:4000]
