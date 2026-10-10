#!/usr/bin/env python3
"""
Ingest CAP V-SAR notes and documentation into ragd, following the house chunking conventions.

ragd does not chunk server-side - the caller does. The existing index uses a
purpose-built pipeline whose output shape was reverse-engineered from live
chunks, because the real ingester lives in /home/ron/ragd/ on cainfra02 and is
not reachable from here:

  metadata = {path, title, chunk, chunks?, kind, authority}
    kind      "prose"      free text, chunks counted, no breadcrumb
              "table_row"  one chunk per row, breadcrumbed
    chunks    present on prose only
    authority Projects/as-built/ -> 1.15   (matches AsBuilt_LabInfra, LAB.md)
              Projects/cap-vsar/ -> 1.05   (matches CHANGELOG, trial logs)
              Projects/architecture/ -> 0.85 (matches PATTERN-ai-assisted-*)
    chunk     running index across the whole document, both kinds

Table rows are rendered as   "<title> — <section>. col: val; col: val"
which is what the live index contains.

Ids are "<path>#<n>", so re-running upserts rather than duplicating.

Usage:
    python3 docs/ragd/ragd_ingest.py                     # ingest all standard docs
    python3 docs/ragd/ragd_ingest.py --changelog         # ingest CHANGELOG.md only
    python3 docs/ragd/ragd_ingest.py --analysis          # ingest analysis doc only
    python3 docs/ragd/ragd_ingest.py --dry-run           # preview chunks without sending
    python3 docs/ragd/ragd_ingest.py --file <path> --vpath <vault_path>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import urllib.request

DEFAULT_RAGD = "http://192.0.2.122:7860"
DEFAULT_COLLECTION = "vault"
PROSE_TARGET = 1200
DEFAULT_BATCH_SIZE = 50

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

AUTHORITY = [
    ("Projects/as-built/", 1.15),
    ("Projects/cap-vsar/", 1.05),
    ("Projects/architecture/", 0.85),
    ("Projects/runbooks/", 1.0),
    ("website/", 0.45),
]

STANDARD_FILES = [
    ("Projects/architecture/CONOPS-cap-vsar.md", "docs/ragd/vaultnotes/CONOPS-cap-vsar.md"),
    ("Projects/as-built/AsBuilt_CAPVSAR.md",     "docs/ragd/vaultnotes/AsBuilt_CAPVSAR.md"),
    ("Projects/cap-vsar/CHANGELOG.md",            "CHANGELOG.md"),
    ("Projects/architecture/ANALYSIS-unattended-sar-and-flight-test.md", "docs/ANALYSIS_UNATTENDED_SAR_AND_FLIGHT_TEST.md"),
    ("Projects/architecture/HANDOFF_FAIL_TO_INTENT_CONCEPT.md", "docs/HANDOFF_FAIL_TO_INTENT_CONCEPT.md"),
    ("Projects/architecture/FLIGHT_MODE_ARCHITECTURE_REVIEW_2026-09-17.md", "docs/FLIGHT_MODE_ARCHITECTURE_REVIEW_2026-09-17.md"),
    ("Projects/cap-vsar/ARDUPLANE_TRIAL.md",      "docs/ARDUPLANE_TRIAL.md"),
]


def authority_for(path: str) -> float:
    for prefix, w in AUTHORITY:
        if path.startswith(prefix):
            return w
    return 1.0


def split_table(block: str):
    """Return (header, rows) for a markdown table block, or None."""
    lines = [l for l in block.strip().split("\n") if l.strip()]
    if len(lines) < 3 or not lines[0].lstrip().startswith("|"):
        return None
    if not re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[1]):
        return None
    cells = lambda l: [c.strip() for c in l.strip().strip("|").split("|")]
    return cells(lines[0]), [cells(l) for l in lines[2:]]


def chunk_document(path: str, text: str):
    """Yield (kind, text) in document order."""
    title = "Untitled"
    m = re.search(r'^#\s+(.+)$', text, re.M)
    if m:
        title = m.group(1).strip()

    # split into sections on ## / ### headings, keeping the heading
    parts = re.split(r'^(#{2,3}\s+.+)$', text, flags=re.M)
    section = ""
    out = []
    pending = []

    def flush_prose():
        """Pack accumulated paragraphs into ~PROSE_TARGET chunks."""
        cur = ""
        for p in pending:
            if cur and len(cur) + len(p) + 2 > PROSE_TARGET:
                out.append(("prose", cur.strip()))
                cur = p
            else:
                cur = (cur + "\n\n" + p) if cur else p
        if cur.strip():
            out.append(("prose", cur.strip()))
        pending.clear()

    for part in parts:
        if re.match(r'^#{2,3}\s+', part or ""):
            flush_prose()
            section = part.lstrip("#").strip()
            pending.append(part.strip())
            continue
        for block in re.split(r'\n\s*\n', part or ""):
            if not block.strip():
                continue
            tbl = split_table(block)
            if tbl:
                flush_prose()
                header, rows = tbl
                for row in rows:
                    pairs = "; ".join(f"{h}: {v}" for h, v in zip(header, row) if v)
                    if pairs:
                        head = f"{title} — {section}. " if section else f"{title}. "
                        out.append(("table_row", head + pairs))
            else:
                pending.append(block.strip())
    flush_prose()
    return title, out


def build(path: str, text: str):
    title, chunks = chunk_document(path, text)
    n_prose = sum(1 for k, _ in chunks if k == "prose")
    auth = authority_for(path)
    docs = []
    for i, (kind, body) in enumerate(chunks):
        md = {
            "path": path,
            "title": title,
            "chunk": i,
            "kind": kind,
            "authority": auth,
        }
        if kind == "prose":
            md["chunks"] = n_prose
        docs.append({"id": f"{path}#{i}", "text": body, "metadata": md})
    return docs


def resolve_local_path(local_rel: str) -> Path:
    p = Path(local_rel)
    if p.is_file():
        return p
    # Try relative to repo root
    p_repo = REPO_ROOT / local_rel
    if p_repo.is_file():
        return p_repo
    # Try relative to docs/ragd
    p_ragd = REPO_ROOT / "docs" / "ragd" / local_rel
    if p_ragd.is_file():
        return p_ragd
    raise FileNotFoundError(f"Cannot resolve local file: {local_rel}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest documentation into ragd.")
    ap.add_argument("--dry-run", action="store_true", help="Print summary without posting to ragd")
    ap.add_argument("--ragd-url", default=DEFAULT_RAGD, help="Base URL of ragd server")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION, help="Destination collection name")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Chunks per HTTP POST")
    ap.add_argument("--changelog", action="store_true", help="Ingest CHANGELOG.md only")
    ap.add_argument("--analysis", action="store_true", help="Ingest ANALYSIS_UNATTENDED_SAR_AND_FLIGHT_TEST.md only")
    ap.add_argument("--file", help="Specific local file path to ingest")
    ap.add_argument("--vpath", help="Vault path for --file (e.g. Projects/cap-vsar/foo.md)")
    a = ap.parse_args()

    target_files = []
    if a.file:
        if not a.vpath:
            print("error: --vpath is required when --file is specified", file=sys.stderr)
            return 2
        target_files.append((a.vpath, a.file))
    elif a.changelog:
        target_files.append(("Projects/cap-vsar/CHANGELOG.md", "CHANGELOG.md"))
    elif a.analysis:
        target_files.append((
            "Projects/architecture/ANALYSIS-unattended-sar-and-flight-test.md",
            "docs/ANALYSIS_UNATTENDED_SAR_AND_FLIGHT_TEST.md"
        ))
    else:
        target_files = list(STANDARD_FILES)

    all_docs = []
    print(f"Preparing ingestion into '{a.collection}' at {a.ragd_url}:")
    for vpath, local in target_files:
        try:
            resolved_path = resolve_local_path(local)
            content = resolved_path.read_text(encoding="utf-8")
        except FileNotFoundError as err:
            print(f"  [SKIPPED] {vpath}: {err}", file=sys.stderr)
            continue

        docs = build(vpath, content)
        kinds = {}
        for d in docs:
            kinds[d["metadata"]["kind"]] = kinds.get(d["metadata"]["kind"], 0) + 1
        print(f"  + {vpath} (from {resolved_path.name}): {len(docs)} chunks {kinds} authority={docs[0]['metadata']['authority']}")
        all_docs.extend(docs)

    print(f"\nTotal chunks prepared: {len(all_docs)}")

    if a.dry_run:
        print("\n--- Dry Run Preview (first 3 chunks) ---")
        for d in all_docs[:3]:
            print(f"\n[{d['id']}] kind={d['metadata']['kind']} authority={d['metadata']['authority']}")
            print(d["text"][:200] + ("..." if len(d["text"]) > 200 else ""))
        print("\nDry run completed. No data sent to server.")
        return 0

    # Ingest in batches to handle large documents robustly
    print(f"\nPosting to {a.ragd_url}/ingest in batches of {a.batch_size} chunks...")
    n_batches = (len(all_docs) + a.batch_size - 1) // a.batch_size
    for b_idx in range(n_batches):
        start = b_idx * a.batch_size
        end = min(start + a.batch_size, len(all_docs))
        batch = all_docs[start:end]

        body = json.dumps({"collection": a.collection, "docs": batch}).encode("utf-8")
        req = urllib.request.Request(
            f"{a.ragd_url}/ingest",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                resp_text = resp.read().decode("utf-8", errors="replace").strip()
                print(f"  Batch {b_idx + 1}/{n_batches} [{start}..{end-1}]: HTTP {resp.status} - {resp_text[:80]}")
        except Exception as exc:
            print(f"  Batch {b_idx + 1}/{n_batches} FAILED: {exc}", file=sys.stderr)
            return 1

    print("\nIngestion completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
