#!/usr/bin/env python3
"""
Ingest CAP V-SAR notes into ragd, following the house chunking conventions.

ragd does not chunk server-side - the caller does. The existing index uses a
purpose-built pipeline whose output shape was reverse-engineered from live
chunks, because the real ingester lives in /home/ron/ragd/ on cainfra02 and is
not reachable from here:

  metadata = {path, title, chunk, chunks?, kind, authority}
    kind      "prose"      free text, chunks counted, no breadcrumb
              "table_row"  one chunk per row, breadcrumbed
    chunks    present on prose only
    authority Projects/as-built/ -> 1.15   (matches AsBuilt_LabInfra, LAB.md)
              Projects/architecture/ -> 0.85 (matches PATTERN-ai-assisted-*)
    chunk     running index across the whole document, both kinds

Table rows are rendered as   "<title> — <section>. col: val; col: val"
which is what the live index contains.

Ids are "<path>#<n>", so re-running upserts rather than duplicating.

    python3 ragd_ingest.py            # ingest
    python3 ragd_ingest.py --dry-run  # show what would be sent
"""
import argparse, json, re, sys, urllib.request

RAGD = "http://192.0.2.122:7860"
COLLECTION = "vault"
PROSE_TARGET = 1200

AUTHORITY = [("Projects/as-built/", 1.15), ("Projects/architecture/", 0.85),
             ("Projects/runbooks/", 1.0), ("website/", 0.45)]


def authority_for(path):
    for prefix, w in AUTHORITY:
        if path.startswith(prefix):
            return w
    return 1.0


def split_table(block):
    """Return (header, rows) for a markdown table block, or None."""
    lines = [l for l in block.strip().split("\n") if l.strip()]
    if len(lines) < 3 or not lines[0].lstrip().startswith("|"):
        return None
    if not re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[1]):
        return None
    cells = lambda l: [c.strip() for c in l.strip().strip("|").split("|")]
    return cells(lines[0]), [cells(l) for l in lines[2:]]


def chunk_document(path, text):
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
                out.append(("prose", cur.strip())); cur = p
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


def build(path, text):
    title, chunks = chunk_document(path, text)
    n_prose = sum(1 for k, _ in chunks if k == "prose")
    auth = authority_for(path)
    docs = []
    for i, (kind, body) in enumerate(chunks):
        md = {"path": path, "title": title, "chunk": i,
              "kind": kind, "authority": auth}
        if kind == "prose":
            md["chunks"] = n_prose
        docs.append({"id": f"{path}#{i}", "text": body, "metadata": md})
    return docs


FILES = [("Projects/architecture/CONOPS-cap-vsar.md", "vaultnotes/CONOPS-cap-vsar.md"),
         ("Projects/as-built/AsBuilt_CAPVSAR.md",     "vaultnotes/AsBuilt_CAPVSAR.md")]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    all_docs = []
    for vpath, local in FILES:
        docs = build(vpath, open(local, encoding="utf-8").read())
        kinds = {}
        for d in docs:
            kinds[d["metadata"]["kind"]] = kinds.get(d["metadata"]["kind"], 0) + 1
        print(f"  {vpath}: {len(docs)} chunks {kinds} authority={docs[0]['metadata']['authority']}")
        all_docs += docs

    if a.dry_run:
        for d in all_docs[:4]:
            print("\n---", d["id"], d["metadata"]["kind"])
            print(d["text"][:220])
        sys.exit(0)

    body = json.dumps({"collection": COLLECTION, "docs": all_docs}).encode()
    req = urllib.request.Request(RAGD + "/ingest", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        print("ingest ->", r.status, r.read().decode()[:200])
