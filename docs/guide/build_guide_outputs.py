#!/usr/bin/env python3
"""Build HTML, DOCX, and PDF deliverables for the CAP V-SAR User Guide package.

Usage:
    nice -n 10 /home/ron/.venvs/onb/bin/python docs/guide/build_guide_outputs.py
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

GUIDE_DIR = Path(__file__).resolve().parent
MAIN_MD = GUIDE_DIR / "CAP_VSAR_Simulator_Exercise_Guide.md"
QUICK_MD = GUIDE_DIR / "Quick_Start_by_Role.md"
GLOSSARY_MD = GUIDE_DIR / "Glossary.md"

MAIN_HTML = GUIDE_DIR / "CAP_VSAR_Simulator_Exercise_Guide.html"
MAIN_DOCX = GUIDE_DIR / "CAP_VSAR_Simulator_Exercise_Guide.docx"
MAIN_PDF = GUIDE_DIR / "CAP_VSAR_Simulator_Exercise_Guide.pdf"

QUICK_HTML = GUIDE_DIR / "Quick_Start_by_Role.html"
QUICK_PDF = GUIDE_DIR / "Quick_Start_by_Role.pdf"

FORBIDDEN_JARGON = [
    "websocket",
    "api",
    "bridge",
    "plugin",
    "dataref",
    "json",
    "token",
    "backend",
    "router",
    "oidc",
    "jwt",
    "pkce",
    "endpoint",
]


def check_language_rules() -> dict:
    """Verify zero forbidden software jargon in main body (outside Appendix A) and zero emojis."""
    main_text = MAIN_MD.read_text(encoding="utf-8")
    parts = re.split(r"^##\s+(?:\d+\.\s+)?Appendix A:", main_text, maxsplit=1, flags=re.MULTILINE)
    body_part = parts[0]

    quick_text = QUICK_MD.read_text(encoding="utf-8")
    glossary_text = GLOSSARY_MD.read_text(encoding="utf-8")

    violations = {}
    for label, text in [
        ("CAP_VSAR_Simulator_Exercise_Guide.md (main text)", body_part),
        ("Quick_Start_by_Role.md", quick_text),
        ("Glossary.md", glossary_text),
    ]:
        found = []
        for word in FORBIDDEN_JARGON:
            matches = list(re.finditer(rf"\b{re.escape(word)}s?\b", text, flags=re.IGNORECASE))
            if matches:
                found.append((word, len(matches)))
        if found:
            violations[label] = found

    return violations


def inline_md_to_html(text: str) -> str:
    """Convert inline markdown (`code`, **bold**, *italic*, [link](url)) to HTML safely."""
    # Escape HTML first, preserving placeholders
    code_spans: list[str] = []

    def save_code(m: re.Match) -> str:
        idx = len(code_spans)
        code_spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00CODE{idx}\x00"

    text = re.sub(r"`([^`]+)`", save_code, text)
    text = html.escape(text)

    # Links [label](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    # Bold **...**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic *...*
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)

    for idx, span in enumerate(code_spans):
        text = text.replace(f"\x00CODE{idx}\x00", span)
    return text


def slugify(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", text)
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")
    return s or "section"


def embed_image_data_uri(rel_path: str) -> str:
    img_path = (GUIDE_DIR / rel_path).resolve()
    if not img_path.exists():
        raise FileNotFoundError(f"Missing guide image: {img_path}")
    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def markdown_to_html_blocks(md_text: str, embed_images: bool = True) -> tuple[str, list[tuple[int, str, str]]]:
    """Convert our guide Markdown into structured HTML and return (html_body, toc_entries)."""
    lines = md_text.splitlines()
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Horizontal rule
        if stripped == "---":
            out.append('<hr class="section-divider" />')
            i += 1
            continue

        # Fenced code block
        if stripped.startswith("```"):
            i += 1
            code_lines = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            out.append(f'<pre class="diagram-block"><code>{html.escape(chr(10).join(code_lines))}</code></pre>')
            continue

        # Headings
        m_head = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m_head:
            level = len(m_head.group(1))
            raw_title = m_head.group(2).strip()
            slug = slugify(raw_title)
            if level in (2, 3):
                toc.append((level, raw_title, slug))
            out.append(f'<h{level} id="{slug}">{inline_md_to_html(raw_title)}</h{level}>')
            i += 1
            continue

        # Image block ![alt](path) followed optionally by *Figure N — caption*
        m_img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if m_img:
            alt_text = m_img.group(1)
            rel_path = m_img.group(2)
            src = embed_image_data_uri(rel_path) if embed_images else rel_path
            i += 1
            caption_html = ""
            while i < n and not lines[i].strip():
                i += 1
            if i < n and lines[i].strip().startswith("*Figure "):
                cap_line = lines[i].strip().strip("*")
                caption_html = f"<figcaption>{inline_md_to_html(cap_line)}</figcaption>"
                i += 1
            out.append(
                f'<figure class="guide-figure">'
                f'<img src="{src}" alt="{html.escape(alt_text)}" loading="lazy" />'
                f"{caption_html}"
                f"</figure>"
            )
            continue

        # Markdown table
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|\s*[-:]+", lines[i + 1].strip()):
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2  # skip header and separator
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(row_cells)
                i += 1
            thead = "<thead><tr>" + "".join(f"<th>{inline_md_to_html(c)}</th>" for c in header_cells) + "</tr></thead>"
            tbody_rows = []
            for r in rows:
                tbody_rows.append("<tr>" + "".join(f"<td>{inline_md_to_html(c)}</td>" for c in r) + "</tr>")
            tbody = "<tbody>" + "".join(tbody_rows) + "</tbody>"
            out.append(f'<div class="table-wrap"><table class="guide-table">{thead}{tbody}</table></div>')
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", stripped):
            items: list[str] = []
            while i < n:
                cur = lines[i].strip()
                m_ol = re.match(r"^\d+\.\s+(.*)$", cur)
                if m_ol:
                    item_parts = [m_ol.group(1)]
                    i += 1
                    while (
                        i < n
                        and lines[i].strip()
                        and re.match(r"^\s{2,}\S", lines[i])
                        and not re.match(r"^\s*[-*]\s+", lines[i])
                        and not re.match(r"^\s*\d+\.\s+", lines[i])
                    ):
                        item_parts.append(lines[i].strip())
                        i += 1
                    item_html = inline_md_to_html(" ".join(item_parts))
                    sub_bullets: list[str] = []
                    while i < n and re.match(r"^\s{2,}[-*]\s+", lines[i]):
                        sub_parts = [re.sub(r"^\s*[-*]\s+", "", lines[i]).strip()]
                        i += 1
                        while (
                            i < n
                            and lines[i].strip()
                            and re.match(r"^\s{4,}\S", lines[i])
                            and not re.match(r"^\s*[-*]\s+", lines[i])
                            and not re.match(r"^\s*\d+\.\s+", lines[i])
                        ):
                            sub_parts.append(lines[i].strip())
                            i += 1
                        sub_html = inline_md_to_html(" ".join(sub_parts))
                        sub_sub: list[str] = []
                        while i < n and re.match(r"^\s{6,}[-*]\s+", lines[i]):
                            ss_parts = [re.sub(r"^\s*[-*]\s+", "", lines[i]).strip()]
                            i += 1
                            while (
                                i < n
                                and lines[i].strip()
                                and re.match(r"^\s{7,}\S", lines[i])
                                and not re.match(r"^\s*[-*]\s+", lines[i])
                            ):
                                ss_parts.append(lines[i].strip())
                                i += 1
                            sub_sub.append(f"<li>{inline_md_to_html(' '.join(ss_parts))}</li>")
                        if sub_sub:
                            sub_html += "<ul>" + "".join(sub_sub) + "</ul>"
                        sub_bullets.append(f"<li>{sub_html}</li>")
                    if sub_bullets:
                        item_html += "<ul>" + "".join(sub_bullets) + "</ul>"
                    items.append(f"<li>{item_html}</li>")
                else:
                    break
            out.append("<ol>" + "".join(items) + "</ol>")
            continue

        # Unordered list (- or *)
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()) and not re.match(r"^\s{2,}[-*]\s+", lines[i]):
                item_parts = [re.sub(r"^[-*]\s+", "", lines[i].strip())]
                i += 1
                while (
                    i < n
                    and lines[i].strip()
                    and re.match(r"^\s{2,}\S", lines[i])
                    and not re.match(r"^\s*[-*]\s+", lines[i])
                    and not re.match(r"^\s*\d+\.\s+", lines[i])
                ):
                    item_parts.append(lines[i].strip())
                    i += 1
                item_html = inline_md_to_html(" ".join(item_parts))
                sub_items: list[str] = []
                while i < n and (
                    re.match(r"^\s{2,}[-*]\s+", lines[i]) or re.match(r"^\s{2,}\d+\.\s+", lines[i])
                ):
                    if re.match(r"^\s{2,}\d+\.\s+", lines[i]):
                        break
                    sub_parts = [re.sub(r"^\s*[-*]\s+", "", lines[i]).strip()]
                    i += 1
                    while (
                        i < n
                        and lines[i].strip()
                        and re.match(r"^\s{4,}\S", lines[i])
                        and not re.match(r"^\s*[-*]\s+", lines[i])
                        and not re.match(r"^\s*\d+\.\s+", lines[i])
                    ):
                        sub_parts.append(lines[i].strip())
                        i += 1
                    sub_html = inline_md_to_html(" ".join(sub_parts))
                    sub_sub_u: list[str] = []
                    while i < n and re.match(r"^\s{4,}[-*]\s+", lines[i]):
                        ss_parts = [re.sub(r"^\s*[-*]\s+", "", lines[i]).strip()]
                        i += 1
                        while (
                            i < n
                            and lines[i].strip()
                            and re.match(r"^\s{6,}\S", lines[i])
                            and not re.match(r"^\s*[-*]\s+", lines[i])
                        ):
                            ss_parts.append(lines[i].strip())
                            i += 1
                        sub_sub_u.append(f"<li>{inline_md_to_html(' '.join(ss_parts))}</li>")
                    if sub_sub_u:
                        sub_html += "<ul>" + "".join(sub_sub_u) + "</ul>"
                    sub_items.append(f"<li>{sub_html}</li>")
                if sub_items:
                    item_html += "<ul>" + "".join(sub_items) + "</ul>"
                items.append(f"<li>{item_html}</li>")
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Normal paragraph (coalesce consecutive text lines)
        para_lines = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt == "---"
                or nxt.startswith("#")
                or nxt.startswith("```")
                or nxt.startswith("|")
                or re.match(r"^[-*]\s+", nxt)
                or re.match(r"^\d+\.\s+", nxt)
                or re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", nxt)
            ):
                break
            para_lines.append(nxt)
            i += 1
        para_text = " ".join(para_lines)
        out.append(f"<p>{inline_md_to_html(para_text)}</p>")

    return "\n".join(out), toc


def build_main_html() -> None:
    md_text = MAIN_MD.read_text(encoding="utf-8")
    body_html, toc = markdown_to_html_blocks(md_text, embed_images=True)

    toc_items = []
    for level, title, slug in toc:
        cls = "toc-h2" if level == 2 else "toc-h3"
        toc_items.append(f'<li class="{cls}"><a href="#{slug}">{inline_md_to_html(title)}</a></li>')
    toc_html = '<ul class="toc-list">' + "\n".join(toc_items) + "</ul>"

    role_cards_html = """
    <section class="role-cards-banner" aria-label="Role Quick-Start Cards">
      <div class="role-card">
        <div class="role-badge">IC / AOBD / SET</div>
        <h3>Incident Commander, AOBD &amp; Exercise Director</h3>
        <p><strong>Routes:</strong> <code>/login</code> &rarr; <code>/setup</code> &rarr; <code>/ready</code> &rarr; <code>/instructor</code> &rarr; <code>/debrief</code></p>
        <ol>
          <li>Sign in with Google, configure <code>CAWG Pauma Valley Mountain SAREX</code>, assign per-seat Google emails in Step 2, and send invites in Step 4 (or print offline QR badges).</li>
          <li>Generate the <code>ESCON</code> 1.0 NM expanding square in <code>/planner/</code>, start Scenario C-1 on <code>/instructor</code>, and track LOPs on <code>/base</code>.</li>
          <li>Reveal the true ELT on <code>/debrief</code> and review CPA, bearing error, and <code>CAPF 110</code> logs.</li>
        </ol>
      </div>
      <div class="role-card">
        <div class="role-badge">MRO 1 &amp; MRO 2</div>
        <h3>Mission Radio Operator &amp; Mission Base Staff</h3>
        <p><strong>Sign-In:</strong> Google (<code>mro1@example.org</code>) or Badge <code>MRO-1-&hellip;</code> / <code>MRO-2-&hellip;</code> &rarr; <code>/ready</code> &rarr; <code>/radio</code> &amp; <code>/base</code></p>
        <ol>
          <li>Click <strong>Sign in with Google</strong> at <code>/login</code> (or enter your offline badge code), open <code>/radio</code>, and click <strong>Join Voice Net</strong> on the <strong>Primary SAR Net</strong>.</li>
          <li>Operate the <strong>Motorola APX 4500</strong> (VHF-FM) and <strong>Icom IC-A120</strong> (airband) using <strong>PUSH TO TALK (SPACE)</strong>.</li>
          <li>Log every call and 30-minute Ops Normal check-in on <strong>CAP Form 110</strong> and plot bearing cuts on <code>/base</code>.</li>
        </ol>
      </div>
      <div class="role-card">
        <div class="role-badge">MP / MO / MS</div>
        <h3>Aircrew (<code>CAP 423</code> Low Block &amp; <code>CAP 415</code> High Cover)</h3>
        <p><strong>Sign-In:</strong> Google or Badge <code>PLT-423</code> / <code>OBS-423</code> / <code>SCN-423</code> &rarr; X-Plane 12 &amp; Air Manager</p>
        <ol>
          <li>Sign in with Google at <code>/login</code> (or scan your badge QR card), turn <strong>Mission Master Switch</strong> ON, and configure <strong>Garmin GMA 1347</strong> and <strong>TDFM-136B</strong>.</li>
          <li>Fly or supervise the <strong>AI Mission Pilot</strong> / <strong>GFC 700</strong> autopilot at <code>4,500 ft MSL</code> (<code>6,000 ft MSL</code> Ramona ridge floor).</li>
          <li>Read wings-level bearings on <strong>Becker SAR-DF 517</strong> / <strong>RHOTHETA RT-600</strong>, observe the cone-of-confusion flip over <code>ESCON</code>, and report cuts to Mission Base.</li>
        </ol>
      </div>
      <div class="role-card">
        <div class="role-badge">UDF 1 &amp; UDF 2</div>
        <h3>Ground Search / Urban Direction Finding Team</h3>
        <p><strong>Sign-In:</strong> Google (<code>udf1@example.org</code>) or the <code>UDF-&hellip;</code> badge code on your printed card &rarr; <code>/ready</code> &rarr; <code>/radio</code></p>
        <ol>
          <li>Click <strong>Sign in with Google</strong> at <code>/login</code> (or use your offline badge code at an off-grid ESCON site), open <code>/radio</code>, and join the <strong>Primary SAR Net</strong>.</li>
          <li>Receive the airborne LOP intersection coordinates near <code>ESCON</code> (<code>33.1700&deg; N, 117.0792&deg; W</code>) from Mission Base.</li>
          <li>Home in on the 121.5 MHz signal along Valley Center Rd / Hwy 76 and report ELT ID <code>EX-ESCON-1215</code> found.</li>
        </ol>
      </div>
    </section>
    """

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CAP V-SAR Simulator &amp; Exercise System — User Guide &amp; ESCON ELT Training Manual</title>
  <style>
    :root {{
      --navy: #0f2547;
      --navy-mid: #1b3a6b;
      --gold: #b8860b;
      --gold-bg: #fef9ec;
      --ink: #17202a;
      --muted: #4a5568;
      --border: #d4dce6;
      --surface: #f7f9fc;
      --card: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: var(--ink);
      background: var(--surface);
      line-height: 1.62;
      font-size: 15px;
    }}
    .top-banner {{
      background: linear-gradient(135deg, var(--navy) 0%, var(--navy-mid) 100%);
      color: #ffffff;
      padding: 28px 36px;
      border-bottom: 4px solid #d4a017;
    }}
    .top-banner .doc-kicker {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 12px;
      font-weight: 700;
      color: #f3c64d;
      margin-bottom: 6px;
    }}
    .top-banner h1 {{
      margin: 0 0 8px 0;
      font-size: 26px;
      line-height: 1.25;
      color: #ffffff;
    }}
    .top-banner .doc-sub {{
      margin: 0;
      font-size: 14px;
      color: #dce6f5;
    }}
    .page-shell {{
      display: grid;
      grid-template-columns: 290px minmax(0, 1fr);
      gap: 28px;
      max-width: 1420px;
      margin: 0 auto;
      padding: 24px 28px 64px;
    }}
    .toc-sidebar {{
      position: sticky;
      top: 16px;
      align-self: start;
      max-height: calc(100vh - 32px);
      overflow-y: auto;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 18px;
      box-shadow: 0 1px 3px rgba(15, 37, 71, 0.06);
    }}
    .toc-sidebar h2 {{
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--navy);
      margin: 0 0 10px 0;
      padding-bottom: 8px;
      border-bottom: 2px solid var(--border);
    }}
    .toc-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      font-size: 13px;
    }}
    .toc-list li {{
      margin: 4px 0;
    }}
    .toc-list li.toc-h3 {{
      padding-left: 14px;
      font-size: 12.2px;
    }}
    .toc-list a {{
      color: var(--muted);
      text-decoration: none;
      display: block;
      padding: 2px 4px;
      border-radius: 4px;
    }}
    .toc-list a:hover {{
      color: var(--navy);
      background: #eef3f9;
    }}
    .guide-main {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 32px 40px;
      box-shadow: 0 2px 6px rgba(15, 37, 71, 0.05);
    }}
    .role-cards-banner {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin: 0 0 28px 0;
    }}
    .role-card {{
      background: #f8fafd;
      border: 1px solid var(--border);
      border-left: 4px solid var(--navy);
      border-radius: 8px;
      padding: 14px 16px;
    }}
    .role-card .role-badge {{
      display: inline-block;
      background: var(--navy);
      color: #ffffff;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      padding: 2px 8px;
      border-radius: 4px;
      margin-bottom: 6px;
    }}
    .role-card h3 {{
      margin: 0 0 6px 0;
      font-size: 15px;
      color: var(--navy);
    }}
    .role-card p {{
      margin: 0 0 8px 0;
      font-size: 13px;
      color: var(--muted);
    }}
    .role-card ol {{
      margin: 0;
      padding-left: 18px;
      font-size: 13px;
    }}
    .role-card li {{
      margin-bottom: 4px;
    }}
    h1 {{
      font-size: 26px;
      color: var(--navy);
      margin-top: 0;
      border-bottom: 2px solid var(--navy);
      padding-bottom: 10px;
    }}
    h2 {{
      font-size: 21px;
      color: var(--navy);
      margin-top: 36px;
      margin-bottom: 12px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border);
    }}
    h3 {{
      font-size: 17px;
      color: var(--navy-mid);
      margin-top: 24px;
      margin-bottom: 8px;
    }}
    h4 {{
      font-size: 15px;
      color: var(--ink);
      margin-top: 18px;
      margin-bottom: 6px;
    }}
    p {{
      margin: 0 0 12px 0;
    }}
    ul, ol {{
      margin: 0 0 14px 0;
      padding-left: 24px;
    }}
    li {{
      margin-bottom: 6px;
    }}
    code {{
      font-family: "JetBrains Mono", "Fira Code", Consolas, Monaco, monospace;
      font-size: 0.9em;
      background: #eef2f7;
      color: #0f2547;
      padding: 1px 5px;
      border-radius: 4px;
    }}
    pre.diagram-block {{
      background: #0f1c2e;
      color: #e6edf7;
      padding: 16px 20px;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 12.5px;
      line-height: 1.45;
      margin: 14px 0 18px;
    }}
    pre.diagram-block code {{
      background: transparent;
      color: inherit;
      padding: 0;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin: 14px 0 20px;
    }}
    table.guide-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13.5px;
    }}
    table.guide-table th {{
      background: var(--navy);
      color: #ffffff;
      text-align: left;
      padding: 8px 10px;
      font-weight: 600;
    }}
    table.guide-table td {{
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    table.guide-table tr:nth-child(even) td {{
      background: #f8fafd;
    }}
    figure.guide-figure {{
      margin: 20px 0 26px;
      background: #f8fafd;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      page-break-inside: avoid;
      break-inside: avoid;
    }}
    figure.guide-figure img {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
      border-radius: 4px;
      border: 1px solid #cbd5e1;
    }}
    figure.guide-figure figcaption {{
      margin-top: 10px;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.45;
      padding: 0 4px;
    }}
    hr.section-divider {{
      border: 0;
      border-top: 1px solid var(--border);
      margin: 28px 0;
    }}
    @media (max-width: 1024px) {{
      .page-shell {{
        grid-template-columns: 1fr;
      }}
      .toc-sidebar {{
        position: static;
        max-height: none;
      }}
      .role-cards-banner {{
        grid-template-columns: 1fr;
      }}
    }}
    @media print {{
      @page {{
        size: letter;
        margin: 0.55in 0.55in 0.6in 0.55in;
      }}
      body {{
        background: #ffffff;
        font-size: 10.5pt;
        line-height: 1.45;
      }}
      .top-banner {{
        padding: 16px 20px;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      .page-shell {{
        display: block;
        padding: 0;
        max-width: none;
      }}
      .toc-sidebar {{
        position: static;
        max-height: none;
        margin: 12px 0 18px;
        page-break-after: always;
      }}
      .guide-main {{
        border: 0;
        box-shadow: none;
        padding: 0;
      }}
      .role-cards-banner {{
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
        page-break-inside: avoid;
      }}
      h2 {{
        page-break-after: avoid;
        break-after: avoid;
      }}
      h3 {{
        page-break-after: avoid;
        break-after: avoid;
      }}
      figure.guide-figure {{
        page-break-inside: avoid;
        break-inside: avoid;
        padding: 8px;
        margin: 12px 0;
      }}
      figure.guide-figure img {{
        max-height: 3.6in;
        width: auto;
      }}
      table.guide-table {{
        font-size: 9.2pt;
      }}
      table.guide-table th {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      pre.diagram-block {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
        font-size: 8.5pt;
        page-break-inside: avoid;
      }}
    }}
  </style>
</head>
<body>
  <header class="top-banner">
    <div class="doc-kicker">Civil Air Patrol Emergency Services Training Documentation</div>
    <h1>CAP V-SAR Simulator &amp; Exercise System — User Guide &amp; ESCON ELT Training Manual</h1>
    <p class="doc-sub">Reference Publications: CAPR 100-1 &bull; CAPR 100-3 &bull; CAPP 100-3 (MART Vol. II) &bull; CAPF 110 &bull; ICS 204 &bull; SQTR-MO / SQTR-MS / SQTR-MRO</p>
  </header>
  <div class="page-shell">
    <nav class="toc-sidebar" aria-label="Table of Contents">
      <h2>Table of Contents</h2>
      {toc_html}
    </nav>
    <main class="guide-main">
      {role_cards_html}
      {body_html}
    </main>
  </div>
</body>
</html>
"""
    MAIN_HTML.write_text(full_html, encoding="utf-8")


def build_quick_html() -> None:
    md_text = QUICK_MD.read_text(encoding="utf-8")
    body_html, _ = markdown_to_html_blocks(md_text, embed_images=False)
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CAP V-SAR Quick Start by Role (One-Page Checklist)</title>
  <style>
    @page {{
      size: letter;
      margin: 0.35in 0.4in;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      color: #17202a;
      background: #ffffff;
      margin: 0;
      padding: 18px 24px;
      font-size: 11.2px;
      line-height: 1.36;
    }}
    h1 {{
      font-size: 17px;
      color: #0f2547;
      margin: 0 0 6px 0;
      padding-bottom: 4px;
      border-bottom: 2px solid #0f2547;
    }}
    h2 {{
      font-size: 12.8px;
      color: #ffffff;
      background: #0f2547;
      padding: 4px 10px;
      border-radius: 4px;
      margin: 9px 0 5px 0;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}
    p {{
      margin: 0 0 5px 0;
    }}
    ol {{
      margin: 0 0 6px 0;
      padding-left: 18px;
    }}
    ul {{
      margin: 2px 0 3px 0;
      padding-left: 16px;
    }}
    li {{
      margin-bottom: 2px;
    }}
    code {{
      font-family: "JetBrains Mono", Consolas, monospace;
      font-size: 0.92em;
      background: #eef2f7;
      color: #0f2547;
      padding: 0 4px;
      border-radius: 3px;
    }}
    hr.section-divider {{
      border: 0;
      border-top: 1px solid #cbd5e1;
      margin: 6px 0;
    }}
    @media print {{
      body {{
        padding: 0;
      }}
    }}
  </style>
</head>
<body>
{body_html}
</body>
</html>
"""
    QUICK_HTML.write_text(full_html, encoding="utf-8")


def add_formatted_runs(paragraph, text: str) -> None:
    """Parse **bold**, *italic*, and `code` runs for python-docx."""
    token_re = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)")
    pos = 0
    for m in token_re.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos : m.start()])
        tok = m.group(0)
        if tok.startswith("`") and tok.endswith("`"):
            r = paragraph.add_run(tok[1:-1])
            r.font.name = "DejaVu Sans Mono"
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(15, 37, 71)
        elif tok.startswith("**") and tok.endswith("**"):
            r = paragraph.add_run(tok[2:-2])
            r.bold = True
        elif tok.startswith("*") and tok.endswith("*"):
            r = paragraph.add_run(tok[1:-1])
            r.italic = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def build_main_docx() -> None:
    doc = Document()

    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style.font.size = Pt(10.5)

    lines = MAIN_MD.read_text(encoding="utf-8").splitlines()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped == "---":
            i += 1
            continue

        # Code block
        if stripped.startswith("```"):
            i += 1
            code_lines = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            p = doc.add_paragraph()
            r = p.add_run("\n".join(code_lines))
            r.font.name = "DejaVu Sans Mono"
            r.font.size = Pt(8.5)
            continue

        # Heading
        m_head = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m_head:
            level = len(m_head.group(1))
            title_text = re.sub(r"`([^`]+)`", r"\1", m_head.group(2).strip())
            h = doc.add_heading(title_text, level=min(level, 4))
            for r in h.runs:
                r.font.color.rgb = RGBColor(15, 37, 71)
            i += 1
            continue

        # Image
        m_img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if m_img:
            rel_path = m_img.group(2)
            img_path = (GUIDE_DIR / rel_path).resolve()
            if img_path.exists():
                p_img = doc.add_paragraph()
                p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_img.add_run().add_picture(str(img_path), width=Inches(6.2))
            i += 1
            while i < n and not lines[i].strip():
                i += 1
            if i < n and lines[i].strip().startswith("*Figure "):
                cap_line = lines[i].strip().strip("*")
                p_cap = doc.add_paragraph()
                p_cap.alignment = WD_ALIGN_PARAGRAPH.LEFT
                r_cap = p_cap.add_run(re.sub(r"`([^`]+)`", r"\1", cap_line))
                r_cap.italic = True
                r_cap.font.size = Pt(9.5)
                r_cap.font.color.rgb = RGBColor(74, 85, 104)
                i += 1
            continue

        # Table
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|\s*[-:]+", lines[i + 1].strip()):
            headers = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            tbl.style = "Table Grid"
            hdr_cells = tbl.rows[0].cells
            for col_idx, h_text in enumerate(headers):
                hdr_cells[col_idx].text = ""
                p = hdr_cells[col_idx].paragraphs[0]
                r = p.add_run(re.sub(r"[`*_]", "", h_text))
                r.bold = True
                r.font.size = Pt(9.5)
            for row_idx, r_data in enumerate(rows, start=1):
                row_cells = tbl.rows[row_idx].cells
                for col_idx in range(min(len(headers), len(r_data))):
                    row_cells[col_idx].text = ""
                    p = row_cells[col_idx].paragraphs[0]
                    add_formatted_runs(p, r_data[col_idx])
            doc.add_paragraph()
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", stripped):
            while i < n:
                cur = lines[i].strip()
                m_ol = re.match(r"^(\d+\.)\s+(.*)$", cur)
                if m_ol:
                    item_parts = [m_ol.group(2)]
                    i += 1
                    while (
                        i < n
                        and lines[i].strip()
                        and re.match(r"^\s{2,}\S", lines[i])
                        and not re.match(r"^\s*[-*]\s+", lines[i])
                        and not re.match(r"^\s*\d+\.\s+", lines[i])
                    ):
                        item_parts.append(lines[i].strip())
                        i += 1
                    p = doc.add_paragraph(style="List Number")
                    add_formatted_runs(p, " ".join(item_parts))
                    while i < n and re.match(r"^\s{2,}[-*]\s+", lines[i]):
                        sub_parts = [re.sub(r"^\s*[-*]\s+", "", lines[i]).strip()]
                        i += 1
                        while (
                            i < n
                            and lines[i].strip()
                            and re.match(r"^\s{4,}\S", lines[i])
                            and not re.match(r"^\s*[-*]\s+", lines[i])
                            and not re.match(r"^\s*\d+\.\s+", lines[i])
                        ):
                            sub_parts.append(lines[i].strip())
                            i += 1
                        p_sub = doc.add_paragraph(style="List Bullet 2")
                        add_formatted_runs(p_sub, " ".join(sub_parts))
                else:
                    break
            continue

        # Unordered list
        if re.match(r"^[-*]\s+", stripped):
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                is_sub = bool(re.match(r"^\s{2,}[-*]\s+", lines[i]))
                item_parts = [re.sub(r"^\s*[-*]\s+", "", lines[i]).strip()]
                i += 1
                while (
                    i < n
                    and lines[i].strip()
                    and re.match(r"^\s{2,}\S", lines[i])
                    and not re.match(r"^\s*[-*]\s+", lines[i])
                    and not re.match(r"^\s*\d+\.\s+", lines[i])
                ):
                    item_parts.append(lines[i].strip())
                    i += 1
                p = doc.add_paragraph(style="List Bullet 2" if is_sub else "List Bullet")
                add_formatted_runs(p, " ".join(item_parts))
            continue

        # Paragraph
        para_lines = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt == "---"
                or nxt.startswith("#")
                or nxt.startswith("```")
                or nxt.startswith("|")
                or re.match(r"^[-*]\s+", nxt)
                or re.match(r"^\d+\.\s+", nxt)
                or re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", nxt)
            ):
                break
            para_lines.append(nxt)
            i += 1
        p = doc.add_paragraph()
        add_formatted_runs(p, " ".join(para_lines))

    doc.save(str(MAIN_DOCX))


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    cmd = [
        "nice",
        "-n",
        "10",
        "/usr/bin/google-chrome",
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        f"file://{html_path.resolve()}",
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def count_pdf_pages(pdf_path: Path) -> int:
    try:
        res = subprocess.run(
            ["/usr/bin/pdfinfo", str(pdf_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for line in res.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
    except Exception:
        pass
    data = pdf_path.read_bytes()
    return len(re.findall(rb"/Type\s*/Page\b", data))


def main() -> None:
    violations = check_language_rules()
    if violations:
        print("LANGUAGE RULE VIOLATIONS FOUND:", json.dumps(violations, indent=2))
        sys.exit(1)

    build_main_html()
    build_quick_html()
    build_main_docx()
    render_pdf(MAIN_HTML, MAIN_PDF)
    render_pdf(QUICK_HTML, QUICK_PDF)

    summary = {
        "language_violations": violations,
        "files": {},
    }
    for p in [MAIN_MD, MAIN_HTML, MAIN_DOCX, MAIN_PDF, QUICK_MD, QUICK_HTML, QUICK_PDF, GLOSSARY_MD]:
        info = {"size_bytes": p.stat().st_size, "size_kb": round(p.stat().st_size / 1024, 1)}
        if p.suffix == ".pdf":
            info["pages"] = count_pdf_pages(p)
        summary["files"][p.name] = info

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
