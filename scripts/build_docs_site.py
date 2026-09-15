#!/usr/bin/env python3
"""Build a static documentation site from the documents already in this repo.

The documentation exists but is scattered across four formats and seven
directories, so nobody reads it. This collects it into one browsable site
without becoming a second copy that drifts: every page is GENERATED from the
file in the tree, so the tree stays the single source of truth and a stale site
is fixed by re-running this.

Conversions: .docx via LibreOffice (headless), .md via python-markdown, .html
copied and re-wrapped in the site template, .pdf copied and linked.

    python3 scripts/build_docs_site.py --out build/docs-site
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


@dataclass
class Doc:
    """One document to publish. `source` is relative to the repo root."""
    source: str
    title: str
    blurb: str
    also: list = field(default_factory=list)   # extra formats, e.g. a PDF twin


@dataclass
class Section:
    title: str
    blurb: str
    docs: list


# Ordered by who needs it, not by where it happens to live in the tree.
SECTIONS = [
    Section(
        "Start here",
        "What the system is and how to run an exercise on it.",
        [
            Doc("docs/CAP_V-SAR_User_Guide.docx",
                "CAP V-SAR User Guide",
                "The whole system end to end - exercise console, Mission Base, base "
                "radio, flight planner and debrief - with screenshots of the running "
                "deployment. Start here if you have never used it."),
            Doc("docs/manual/CAP_VSAR_Flight_Operations_Handbook.html",
                "Flight Operations Handbook",
                "Aircrew handbook: the aircraft, its avionics, the DF equipment and "
                "how a sortie is flown.",
                also=[("docs/manual/CAP_VSAR_Flight_Operations_Handbook.pdf", "PDF")]),
        ],
    ),
    Section(
        "Operator guides",
        "One per station. Hand these to the person sitting at that seat.",
        [
            Doc("docs/mission-base-radio/README.md", "Mission Base radio",
                "The base radio console: nets, channels and how base talks to aircraft."),
            Doc("services/flightplanner/docs/USER_GUIDE.md", "Flight planner - user guide",
                "Navigation logs, CAP search patterns (parallel, creeping line, expanding "
                "square) and FMS export."),
            Doc("services/flightplanner/docs/QUICKSTART.md", "Flight planner - quick start",
                "The short version: first route in a few minutes."),
            Doc("services/exercise/README.md", "Exercise service",
                "The exercise console and Mission Base server - scenarios, roles and the "
                "debrief."),
        ],
    ),
    Section(
        "Engineering",
        "Not participant-facing. These describe how the system is built and flown "
        "by its developers.",
        [
            Doc("README.md", "Project README",
                "Architecture, the service map, and how to build and deploy."),
            Doc("services/ai_pilot/README.md", "AI Pilot service",
                "The supervised maneuver gate and the direct surface-control backend "
                "used for flight test. Engineering surface, not a participant one."),
            Doc("services/flightplanner/README.md", "Flight planner service",
                "Deployment and configuration of the planner."),
            Doc("docs/SOURCES.md", "Sources and provenance",
                "Where every manual, dataset and reference in this project came from. "
                "Read this before redistributing anything."),
        ],
    ),
]

# Reference PDFs. Vendor manuals are third-party documents republished here for
# internal training use only - see SOURCES.md. They are listed separately from
# project documents so the distinction stays visible.
PROJECT_PDFS = [
    ("docs/CAP_V-SAR_AI_Mission_Pilot_CONOPS.pdf", "AI Mission Pilot CONOPS"),
    ("docs/CAP_V-SAR_Radio_Features_and_Use_Cases.pdf", "Radio features and use cases"),
    ("docs/RT600_CAP_basic_training.pdf", "RT-600 basic training (CAP)"),
    ("docs/GMA1347_C182T_CAP_audio_panel.pdf", "GMA 1347 audio panel in CAP 487"),
]
VENDOR_PDFS = [
    ("docs/Becker_SARDF517_manual.pdf", "Becker SAR-DF 517 manual"),
    ("docs/Becker_SARDF517_manual_akwg.pdf", "Becker SAR-DF 517 manual (AKWG)"),
    ("docs/RT600_SARDF517_manual.pdf", "RT-600 / SAR-DF 517 manual"),
    ("docs/RT600_america_manual.pdf", "RT-600 manual (America)"),
    ("docs/TDFM136B_operating.pdf", "Technisonic TDFM-136B operating"),
    ("docs/TDFM136_install_operating.pdf", "Technisonic TDFM-136 install and operating"),
    ("docs/GMA1347_garmin_audio_panel_guide.pdf", "Garmin GMA 1347 audio panel guide"),
]

CSS = """
:root{--bg:#fbfaf8;--fg:#1c1b19;--muted:#5d5a55;--line:#e2ded7;--card:#fff;
--accent:#1f5f8b;--accent-soft:#eaf2f8}
@media(prefers-color-scheme:dark){:root{--bg:#16181c;--fg:#e8e6e3;--muted:#a8a49d;
--line:#2c3037;--card:#1d2026;--accent:#7fb6dd;--accent-soft:#1a2733}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:0 20px}
header.top{border-bottom:1px solid var(--line);background:var(--card);
padding-block:28px;margin-bottom:32px}
header.top h1{margin:0 0 6px;font-size:1.6rem;letter-spacing:-.01em}
header.top p{margin:0;color:var(--muted);font-size:.95rem}
h2{margin:36px 0 4px;font-size:1.15rem;letter-spacing:-.01em}
h2+.sec-blurb{margin:0 0 14px;color:var(--muted);font-size:.9rem}
.card{display:block;background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:14px 16px;margin-bottom:10px;text-decoration:none;color:inherit}
.card:hover{border-color:var(--accent);background:var(--accent-soft)}
.card .t{font-weight:600;color:var(--accent)}
.card .b{color:var(--muted);font-size:.9rem;margin-top:3px}
.card .m{color:var(--muted);font-size:.78rem;margin-top:6px;font-variant-numeric:tabular-nums}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;
padding:1px 8px;font-size:.72rem;color:var(--muted);margin-left:6px;vertical-align:middle}
ul.plain{list-style:none;padding:0;margin:0}
ul.plain li{border-bottom:1px solid var(--line);padding:9px 2px;display:flex;
justify-content:space-between;gap:12px;align-items:baseline}
ul.plain li:last-child{border-bottom:0}
ul.plain a{color:var(--accent);text-decoration:none}
ul.plain a:hover{text-decoration:underline}
ul.plain .sz{color:var(--muted);font-size:.8rem;white-space:nowrap;
font-variant-numeric:tabular-nums}
.note{background:var(--accent-soft);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:6px;padding:11px 14px;margin:18px 0;font-size:.88rem;color:var(--muted)}
footer{margin:48px 0 32px;padding-top:16px;border-top:1px solid var(--line);
color:var(--muted);font-size:.8rem}
a.back{display:inline-block;margin-bottom:18px;color:var(--accent);
text-decoration:none;font-size:.9rem}
a.back:hover{text-decoration:underline}
article{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:22px 26px;margin-bottom:28px;overflow-wrap:break-word}
article img{max-width:100%;height:auto;border-radius:6px;border:1px solid var(--line)}
article pre{background:var(--bg);border:1px solid var(--line);border-radius:6px;
padding:11px 13px;overflow-x:auto;font-size:.85rem}
article code{background:var(--bg);border:1px solid var(--line);border-radius:4px;
padding:1px 4px;font-size:.87em}
article pre code{border:0;padding:0;background:0 0}
article table{border-collapse:collapse;width:100%;font-size:.9rem;display:block;overflow-x:auto}
article th,article td{border:1px solid var(--line);padding:6px 9px;text-align:left}
article th{background:var(--accent-soft)}
article h1{font-size:1.45rem;margin-top:0}
article h2{font-size:1.18rem;border-bottom:1px solid var(--line);padding-bottom:4px}
article a{color:var(--accent)}
@media(max-width:560px){article{padding:16px 15px}.wrap{padding:0 14px}}
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div class="wrap">{body}</div></body></html>
"""


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.0f} GB"


def slug(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")


def convert_docx(source: Path, workdir: Path) -> tuple[str, Path]:
    """LibreOffice headless docx -> html. Returns (body_html, media_dir)."""
    out = workdir / slug(source.name)
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "html", "--outdir", str(out), str(source)],
        check=True, capture_output=True, timeout=300,
    )
    produced = next(out.glob("*.html"))
    raw = produced.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<body[^>]*>(.*)</body>", raw, re.S | re.I)
    return (match.group(1) if match else raw), out


def convert_md(source: Path) -> str:
    import markdown
    return markdown.markdown(
        source.read_text(encoding="utf-8", errors="replace"),
        extensions=["extra", "tables", "fenced_code", "toc", "sane_lists"],
    )


def convert_html(source: Path) -> str:
    raw = source.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<body[^>]*>(.*)</body>", raw, re.S | re.I)
    return match.group(1) if match else raw


def build(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = out_dir / "files"
    assets.mkdir(exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="docsite-"))
    cards, missing = {}, []

    for section in SECTIONS:
        for doc in section.docs:
            source = REPO / doc.source
            if not source.exists():
                missing.append(doc.source)
                continue
            name = slug(doc.source) + ".html"
            suffix = source.suffix.lower()
            try:
                if suffix == ".docx":
                    body, media = convert_docx(source, workdir)
                    for image in media.iterdir():
                        if image.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif"}:
                            shutil.copy2(image, out_dir / image.name)
                elif suffix == ".md":
                    body = convert_md(source)
                elif suffix in {".html", ".htm"}:
                    body = convert_html(source)
                else:
                    missing.append(doc.source + " (unsupported)")
                    continue
            except Exception as exc:                       # noqa: BLE001
                missing.append(f"{doc.source} ({type(exc).__name__}: {exc})")
                continue

            extra = ""
            for also_path, label in doc.also:
                also = REPO / also_path
                if also.exists():
                    shutil.copy2(also, assets / also.name)
                    extra += (f'<a class="back" href="files/{also.name}">'
                              f'Download {label} ({human(also.stat().st_size)})</a> ')
            page_body = (
                '<a class="back" href="index.html">&larr; All documentation</a>'
                + (f"<p>{extra}</p>" if extra else "")
                + f"<article>{body}</article>"
            )
            (out_dir / name).write_text(
                PAGE.format(title=html.escape(doc.title), css=CSS, body=page_body),
                encoding="utf-8")
            cards[doc.source] = (name, source.stat().st_size, suffix.lstrip("."))

    # ---- index -----------------------------------------------------------
    parts = [
        '<header class="top"><div class="wrap">'
        "<h1>CAP V-SAR documentation</h1>"
        "<p>Virtual Search and Rescue training system &mdash; "
        "operator guides, aircrew handbook and equipment references.</p>"
        "</div></header>"
    ]
    for section in SECTIONS:
        entries = [d for d in section.docs if d.source in cards]
        if not entries:
            continue
        parts.append(f"<h2>{html.escape(section.title)}</h2>"
                     f'<p class="sec-blurb">{html.escape(section.blurb)}</p>')
        for doc in entries:
            name, size, kind = cards[doc.source]
            parts.append(
                f'<a class="card" href="{name}">'
                f'<div class="t">{html.escape(doc.title)}'
                f'<span class="pill">{kind}</span></div>'
                f'<div class="b">{html.escape(doc.blurb)}</div>'
                f'<div class="m">{html.escape(doc.source)} &middot; {human(size)}</div></a>'
            )

    def pdf_list(items):
        rows = []
        for rel, label in items:
            source = REPO / rel
            if not source.exists():
                missing.append(rel)
                continue
            shutil.copy2(source, assets / source.name)
            rows.append(f'<li><a href="files/{source.name}">{html.escape(label)}</a>'
                        f'<span class="sz">{human(source.stat().st_size)}</span></li>')
        return rows

    project_rows = pdf_list(PROJECT_PDFS)
    if project_rows:
        parts.append('<h2>Project references</h2><p class="sec-blurb">'
                     "Documents written for this project.</p>"
                     f'<ul class="plain">{"".join(project_rows)}</ul>')
    vendor_rows = pdf_list(VENDOR_PDFS)
    if vendor_rows:
        parts.append(
            '<h2>Equipment manuals</h2><p class="sec-blurb">'
            "Manufacturer documentation for the radios and direction finders the "
            "simulation reproduces.</p>"
            '<div class="note"><strong>Third-party documents.</strong> These are '
            "vendor manuals, republished here for internal training reference only. "
            "They are not project work and are not covered by this project's licence "
            "&mdash; see Sources and provenance before redistributing any of them."
            "</div>"
            f'<ul class="plain">{"".join(vendor_rows)}</ul>')

    parts.append(
        "<footer>Generated from the repository by "
        "<code>scripts/build_docs_site.py</code>. Every page here is built from a "
        "file in the source tree, which stays the single source of truth &mdash; "
        "re-run the script rather than editing these pages.</footer>")

    (out_dir / "index.html").write_text(
        PAGE.format(title="CAP V-SAR documentation", css=CSS, body="".join(parts)),
        encoding="utf-8")
    shutil.rmtree(workdir, ignore_errors=True)

    pages = len(cards)
    files = len(list(assets.iterdir()))
    total = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
    print(f"built {pages} pages + {files} downloadable files -> {out_dir}  ({human(total)})")
    if missing:
        print("MISSING or failed (not published):")
        for item in missing:
            print("  -", item)
    return 0 if pages else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="build/docs-site")
    args = parser.parse_args()
    return build((REPO / args.out).resolve())


if __name__ == "__main__":
    sys.exit(main())
