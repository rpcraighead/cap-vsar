#!/usr/bin/env python3
"""Render docs/BUG_TRACKER.md from docs/bugs/tracker.json.

The JSON is the source of truth so the markdown, and anything else that reads
the tracker, cannot drift from each other. Edit the JSON, run this.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "bugs" / "tracker.json"
OUT = ROOT / "docs" / "BUG_TRACKER.md"

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
PRI_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
COMPONENT_NAMES = {
    "plugin": "X-Plane plugin / engine",
    "console-api": "Exercise console (backend)",
    "console-ui": "Exercise console (frontend)",
    "planner": "Flight planner",
    "instruments": "Air Manager instruments",
    "infra": "Deployment / infrastructure",
    "docs": "Docs / record",
}


def sort_key(i: dict) -> tuple:
    return (i["wave"], PRI_ORDER[i["priority"]], SEV_ORDER[i["severity"]], i["id"])


def render() -> str:
    data = json.loads(SRC.read_text())
    meta, clusters, issues = data["meta"], data["clusters"], data["issues"]
    issues = sorted(issues, key=sort_key)

    sev = Counter(i["severity"] for i in issues)
    pri = Counter(i["priority"] for i in issues)
    comp = Counter(i["component"] for i in issues)
    open_n = sum(1 for i in issues if i["status"] == "open")

    L: list[str] = []
    L.append(f"# {meta['title']}")
    L.append("")
    L.append(f"**Generated from `{SRC.relative_to(ROOT)}` by `scripts/render_bug_tracker.py` — edit the JSON, not this file.**")
    L.append("")
    L.append(f"Source analysis: [`{meta['generated_from'].split('/')[-1]}`]({meta['generated_from'].split('/')[-1]}). "
             f"Opened {meta['opened']}. {len(issues)} items, {open_n} open.")
    L.append("")
    L.append(f"{meta['id_scheme']}")
    L.append("")

    L.append("## Counts")
    L.append("")
    L.append("| | critical | high | medium | low | total |")
    L.append("|---|---|---|---|---|---|")
    L.append(f"| by severity | {sev['critical']} | {sev['high']} | {sev['medium']} | {sev['low']} | {len(issues)} |")
    L.append("")
    L.append("| P0 | P1 | P2 | P3 |")
    L.append("|---|---|---|---|")
    L.append(f"| {pri['P0']} | {pri['P1']} | {pri['P2']} | {pri['P3']} |")
    L.append("")
    L.append("| Component | Items |")
    L.append("|---|---|")
    for c, n in sorted(comp.items(), key=lambda kv: -kv[1]):
        L.append(f"| {COMPONENT_NAMES.get(c, c)} | {n} |")
    L.append("")

    L.append("## Priority definitions")
    L.append("")
    for k in ("P0", "P1", "P2", "P3"):
        L.append(f"- **{k}** — {meta['priority'][k]}")
    L.append("")

    L.append("## Waves")
    L.append("")
    L.append(f"_{meta['wave_dates_note']}_")
    L.append("")
    for k in sorted(meta["waves"]):
        n = sum(1 for i in issues if str(i["wave"]) == k)
        L.append(f"- **Wave {k}** ({n} items) — {meta['waves'][k]}")
    L.append("")

    L.append("## Clusters")
    L.append("")
    L.append("A cluster is a PR-sized unit of work: items that touch the same files and should be fixed, reviewed and merged together. The owner hint matters because three agents share this tree.")
    L.append("")
    L.append("| Cluster | Name | Items | Coordination |")
    L.append("|---|---|---|---|")
    for cid, c in clusters.items():
        ids = [i["id"] for i in issues if i["cluster"] == cid]
        L.append(f"| {cid} | {c['name']} | {', '.join(ids) if ids else '—'} | {c['owner_hint']} |")
    L.append("")

    L.append("## Board")
    L.append("")
    for w in sorted({i["wave"] for i in issues}):
        wave_items = [i for i in issues if i["wave"] == w]
        L.append(f"### Wave {w} — {meta['waves'][str(w)]}")
        L.append("")
        L.append("| ID | Pri | Sev | Title | Component | Cluster | Effort | Depends on | Status |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for i in wave_items:
            dep = ", ".join(i["depends_on"]) if i["depends_on"] else "—"
            L.append(
                f"| [{i['id']}](#{i['id'].lower()}) | {i['priority']} | {i['severity']} | {i['title']} "
                f"| {i['component']} | {i['cluster']} | {i['effort']} | {dep} | {i['status']} |"
            )
        L.append("")

    L.append("## Detail")
    L.append("")
    for i in issues:
        L.append(f"### {i['id']}")
        L.append("")
        L.append(f"**{i['title']}**")
        L.append("")
        L.append(f"`{i['priority']}` · `{i['severity']}` · `{i['type']}` · {COMPONENT_NAMES.get(i['component'], i['component'])} "
                 f"· cluster {i['cluster']} ({clusters[i['cluster']]['name']}) · effort {i['effort']} · wave {i['wave']} · **{i['status']}**")
        L.append("")
        L.append(f"- **Files:** {', '.join(f'`{f}`' for f in i['files'])}")
        L.append(f"- **Problem:** {i['problem']}")
        L.append(f"- **Fix:** {i['fix']}")
        L.append(f"- **Done when:** {i['verify']}")
        if i["depends_on"]:
            L.append(f"- **Depends on:** {', '.join(i['depends_on'])}")
        L.append("")

    return "\n".join(L) + "\n"


if __name__ == "__main__":
    OUT.write_text(render())
    print(f"[+] Wrote {OUT.relative_to(ROOT)}")
