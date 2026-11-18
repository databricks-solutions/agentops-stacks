"""Collect repository traffic and star metrics and render the README card.

GitHub keeps traffic data for 14 days only. Each run merges the daily
view and clone counts into a CSV so history accumulates past that window,
records star, fork, and watcher totals, and renders light and dark SVG
cards that the README embeds from the `metrics` branch.

Usage: python repo_metrics.py <output-dir>

Requires the `gh` CLI. GH_TOKEN must be able to read repository traffic
(fine-grained token with "Administration: Read-only" on this repository).
GITHUB_REPOSITORY selects the repository (owner/name).
"""

import csv
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

WINDOW_DAYS = 14

TRAFFIC_CSV = "traffic_daily.csv"
TRAFFIC_FIELDS = ["date", "views", "unique_views", "clones", "unique_clones"]
REPO_CSV = "repo_daily.csv"
REPO_FIELDS = ["date", "stars", "forks", "watchers"]

# Design tokens from the project design guidelines.
THEMES = {
    "light": {
        "bg": "#F7F3EC",
        "surface": "#FFFDF9",
        "border": "#DDD3C4",
        "text": "#2B2520",
        "text_muted": "#6B6158",
        "success": "#5E7A4F",
        "danger": "#9E3B32",
    },
    "dark": {
        "bg": "#1C1814",
        "surface": "#26201A",
        "border": "#3F362D",
        "text": "#EDE6DC",
        "text_muted": "#A89C8E",
        "success": "#8FAA7E",
        "danger": "#D2685E",
    },
}
SERIF = "'Source Serif 4', Georgia, serif"
SANS = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"


def gh_api(path, *, paginate=False, accept=None):
    cmd = ["gh", "api", path]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"gh api {path} failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    if paginate:
        return [item for page in data for item in page]
    return data


def read_rows(path):
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        return {row["date"]: row for row in csv.DictReader(handle) if row["date"]}


def write_rows(path, fields, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow({field: rows[key][field] for field in fields})


def merge_traffic(existing, views, clones):
    """Overwrite each day the API reports. The API's latest day is partial,
    so the next run replaces it with the complete count."""
    merged = {key: dict(row) for key, row in existing.items()}
    for kind, payload in (("views", views), ("clones", clones)):
        for day in payload.get(kind, []):
            key = day["timestamp"][:10]
            row = merged.setdefault(
                key, {field: "0" for field in TRAFFIC_FIELDS} | {"date": key}
            )
            row[kind] = str(day["count"])
            row[f"unique_{kind}"] = str(day["uniques"])
    return merged


def period_total(rows, field, start, end):
    """Sum `field` over [start, end). Returns None unless every day is present."""
    total = 0
    day = start
    while day < end:
        row = rows.get(day.isoformat())
        if row is None:
            return None
        total += int(row[field])
        day += timedelta(days=1)
    return total


def change_vs_previous(rows, field, today):
    current_start = today - timedelta(days=WINDOW_DAYS)
    previous_start = current_start - timedelta(days=WINDOW_DAYS)
    current = period_total(rows, field, current_start, today)
    previous = period_total(rows, field, previous_start, current_start)
    if current is None or not previous:
        return None
    return (current - previous) / previous


def compact(number):
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 10_000:
        return f"{number / 1_000:.0f}k"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(number)


def build_cards(metrics):
    def change_line(change):
        if change is None:
            return None
        sign = "+" if change >= 0 else ""
        return (f"{sign}{change:.0%} vs prior {WINDOW_DAYS} days", change >= 0)

    return [
        {
            "label": f"Views, last {WINDOW_DAYS} days",
            "value": compact(metrics["views"]),
            "detail": f"{compact(metrics['unique_views'])} unique visitors",
            "change": change_line(metrics["views_change"]),
        },
        {
            "label": f"Clones, last {WINDOW_DAYS} days",
            "value": compact(metrics["clones"]),
            "detail": f"{compact(metrics['unique_clones'])} unique cloners",
            "change": change_line(metrics["clones_change"]),
        },
        {
            "label": "Stars",
            "value": compact(metrics["stars"]),
            "detail": f"+{metrics['new_stars']} in last {WINDOW_DAYS} days",
            "change": None,
        },
        {
            "label": "Forks",
            "value": compact(metrics["forks"]),
            "detail": f"{compact(metrics['watchers'])} watchers",
            "change": None,
        },
    ]


def render_svg(cards, updated, theme):
    colors = THEMES[theme]
    width, gap, card_height = 720, 16, 132
    card_width = (width - gap * (len(cards) - 1)) / len(cards)
    top = 56
    margin = 16
    height = top + card_height
    outer_width, outer_height = width + 2 * margin, height + 2 * margin
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{outer_width}" '
        f'height="{outer_height}" viewBox="0 0 {outer_width} {outer_height}" '
        f'role="img" aria-label="Repository activity, updated {updated}">',
        f'<rect width="{outer_width}" height="{outer_height}" rx="8" '
        f'fill="{colors["bg"]}"/>',
        f'<g transform="translate({margin} {margin})">',
        f'<text x="0" y="28" font-family="{SERIF}" font-size="24" font-weight="600" '
        f'fill="{colors["text"]}">Repository activity</text>',
        f'<text x="{width}" y="28" text-anchor="end" font-family="{SANS}" '
        f'font-size="13" font-weight="500" fill="{colors["text_muted"]}">'
        f"Updated {updated}</text>",
    ]
    for index, card in enumerate(cards):
        x = index * (card_width + gap)
        pad = 16
        parts += [
            f'<rect x="{x + 0.5:.1f}" y="{top + 0.5}" width="{card_width - 1:.1f}" '
            f'height="{card_height - 1}" rx="8" fill="{colors["surface"]}" '
            f'stroke="{colors["border"]}"/>',
            f'<text x="{x + pad:.1f}" y="{top + 28}" font-family="{SANS}" '
            f'font-size="13" font-weight="500" fill="{colors["text_muted"]}">'
            f"{escape(card['label'])}</text>",
            f'<text x="{x + pad:.1f}" y="{top + 68}" font-family="{SERIF}" '
            f'font-size="32" font-weight="500" fill="{colors["text"]}" '
            f'style="font-variant-numeric: tabular-nums">{escape(card["value"])}</text>',
            f'<text x="{x + pad:.1f}" y="{top + 94}" font-family="{SANS}" '
            f'font-size="13" fill="{colors["text_muted"]}">'
            f"{escape(card['detail'])}</text>",
        ]
        if card["change"]:
            text, up = card["change"]
            fill = colors["success"] if up else colors["danger"]
            parts.append(
                f'<text x="{x + pad:.1f}" y="{top + 114}" font-family="{SANS}" '
                f'font-size="13" font-weight="500" fill="{fill}">{escape(text)}</text>'
            )
    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def summary_markdown(metrics, referrers, paths, updated):
    lines = [
        f"## Repository activity, {updated}",
        "",
        "| Metric | Total | Unique |",
        "|---|---:|---:|",
        f"| Views, last {WINDOW_DAYS} days | {metrics['views']} | {metrics['unique_views']} |",
        f"| Clones, last {WINDOW_DAYS} days | {metrics['clones']} | {metrics['unique_clones']} |",
        f"| Stars | {metrics['stars']} | +{metrics['new_stars']} in last {WINDOW_DAYS} days |",
        f"| Forks | {metrics['forks']} | |",
        f"| Watchers | {metrics['watchers']} | |",
        "",
        "### Top referrers",
        "",
        "| Referrer | Views | Unique |",
        "|---|---:|---:|",
        *[f"| {r['referrer']} | {r['count']} | {r['uniques']} |" for r in referrers[:5]],
        "",
        "### Top pages",
        "",
        "| Path | Views | Unique |",
        "|---|---:|---:|",
        *[f"| `{p['path']}` | {p['count']} | {p['uniques']} |" for p in paths[:5]],
    ]
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        sys.exit("GITHUB_REPOSITORY must be set to owner/name")

    now = datetime.now(timezone.utc)
    today = now.date()
    since = (now - timedelta(days=WINDOW_DAYS)).isoformat()

    info = gh_api(f"repos/{repo}")
    views = gh_api(f"repos/{repo}/traffic/views?per=day")
    clones = gh_api(f"repos/{repo}/traffic/clones?per=day")
    referrers = gh_api(f"repos/{repo}/traffic/popular/referrers")
    paths = gh_api(f"repos/{repo}/traffic/popular/paths")
    stargazers = gh_api(
        f"repos/{repo}/stargazers?per_page=100",
        paginate=True,
        accept="application/vnd.github.star+json",
    )

    traffic = merge_traffic(read_rows(out / TRAFFIC_CSV), views, clones)
    write_rows(out / TRAFFIC_CSV, TRAFFIC_FIELDS, traffic)

    repo_rows = read_rows(out / REPO_CSV)
    repo_rows[today.isoformat()] = {
        "date": today.isoformat(),
        "stars": str(info["stargazers_count"]),
        "forks": str(info["forks_count"]),
        "watchers": str(info["subscribers_count"]),
    }
    write_rows(out / REPO_CSV, REPO_FIELDS, repo_rows)

    metrics = {
        "views": views["count"],
        "unique_views": views["uniques"],
        "clones": clones["count"],
        "unique_clones": clones["uniques"],
        "views_change": change_vs_previous(traffic, "views", today),
        "clones_change": change_vs_previous(traffic, "clones", today),
        "stars": info["stargazers_count"],
        "new_stars": sum(1 for s in stargazers if s["starred_at"] >= since),
        "forks": info["forks_count"],
        "watchers": info["subscribers_count"],
    }
    updated = today.isoformat()
    cards = build_cards(metrics)
    for theme in THEMES:
        (out / f"activity-{theme}.svg").write_text(render_svg(cards, updated, theme))

    summary = summary_markdown(metrics, referrers, paths, updated)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as handle:
            handle.write(summary)
    else:
        print(summary)


if __name__ == "__main__":
    main()
