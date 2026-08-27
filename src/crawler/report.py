"""Render the end-of-crawl report (Markdown + JSON)."""

from __future__ import annotations

from dataclasses import asdict

from .config import TARGET_COUNT
from .scanner import Finding


def build_json(findings: list[Finding], log: list[dict], stats: dict) -> dict:
    return {
        "stats": stats,
        "passwords_qualified": sorted({f.password for f in findings if f.qualified}),
        "findings": [asdict(f) for f in findings],
        "crawl_log": log,
    }


def build_markdown(findings: list[Finding], log: list[dict], stats: dict) -> str:
    qualified = _dedupe_first(f for f in findings if f.qualified)
    disqualified = _dedupe_first(f for f in findings if not f.qualified)

    lines: list[str] = ["# Crawl report", ""]
    lines += [
        f"- URLs fetched: **{stats['fetched']}**",
        f"- URLs discovered: **{stats['discovered']}**",
        f"- Duration: **{stats['duration_seconds']}s**",
        f"- Qualifying findings: **{len(qualified)} / {TARGET_COUNT if TARGET_COUNT is not None else '?'}**",
        "",
        "## Qualifying passwords",
        "",
    ]
    if qualified:
        lines.append("| # | Password | Found in | Location |")
        lines.append("|---|----------|----------|----------|")
        for i, f in enumerate(sorted(qualified, key=lambda x: x.password), 1):
            lines.append(f"| {i} | `{f.password}` | {f.source_url} | {f.location} |")
    else:
        lines.append("_none yet_")
    lines.append("")

    if disqualified:
        lines += ["## Disqualified (header placeholders — ignored)", ""]
        lines.append("| Password | Found in | Location |")
        lines.append("|----------|----------|----------|")
        for f in sorted(disqualified, key=lambda x: x.password):
            lines.append(f"| `{f.password}` | {f.source_url} | {f.location} |")
        lines.append("")

    if stats.get("review"):
        lines += [
            "## Manual inspection suggested",
            "",
            "Images the automated scan can't fully read (e.g. text drawn into the "
            "pixels). Open these and look; run OCR if available.",
            "",
            "| URL | Reason |",
            "|-----|--------|",
        ]
        for item in stats["review"]:
            lines.append(f"| {item['url']} | {item['reason']} |")
        lines.append("")

    if stats.get("rejected"):
        lines += ["## Frontier rejections (loop guards)", ""]
        for reason, count in sorted(stats["rejected"].items()):
            lines.append(f"- {reason}: {count}")
        lines.append("")

    errors = [r for r in log if r["status"] in ("ERROR", 0) or str(r["status"]).startswith(("4", "5"))]
    if errors:
        lines += ["## Non-2xx / failed fetches", ""]
        lines.append("| URL | Status |")
        lines.append("|-----|--------|")
        for r in errors:
            lines.append(f"| {r['url']} | {r['status']} |")
        lines.append("")

    return "\n".join(lines)


def _dedupe_first(findings) -> list[Finding]:
    out: dict[str, Finding] = {}
    for f in findings:
        out.setdefault(f.password, f)
    return list(out.values())
