#!/usr/bin/env bash
# Build the GitHub-safe copy of CAP V-SAR from this repository (2026-10-12).
#
# Never touches this repository: it clones main only into a NEW directory and
# rewrites that clone. The result has no remote; pushing it is a separate step.
#
#   1. purges, from EVERY commit, the manufacturers' manuals, page extracts and the
#      Garmin text dump (docs/SOURCES.md, D-4/D-5), plus the generated documents and
#      panel previews whose older versions embedded third-party artwork
#   2. re-adds the CURRENT versions of those generated files in one final commit
#   3. maps author/committer emails to the GitHub noreply address
#   4. maps the lab's private LAN addresses into the RFC 5737 documentation range
#      192.0.2.0/24 (same last octet) in files, inside Word/PowerPoint documents,
#      and in commit messages
#   5. verifies the result and exits non-zero if anything is off
#
#   usage: scripts/cap-vsar-github-sanitize.sh [DEST_DIR]
#   needs: git-filter-repo (pip install --target DIR git-filter-repo; set FILTER_REPO
#          to its bin/git-filter-repo and PYTHONPATH to DIR, or have it on PATH),
#          curl + python3 (the GitHub numeric id is fetched once, unauthenticated)
#   env:   GH_USER (default rpcraighead), GH_ID (skip the lookup)
set -euo pipefail
SRC=$(cd "$(dirname "$0")/.." && pwd)
DEST=${1:-"$SRC/../cap-vsar-github-candidate"}
FILTER=${FILTER_REPO:-git-filter-repo}
GH_USER=${GH_USER:-rpcraighead}
WORK=$(mktemp -d /tmp/capvsar-sanitize.XXXXXX)

if [ -z "${GH_ID:-}" ]; then
  GH_ID=$(curl -fsS "https://api.github.com/users/$GH_USER" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
fi
NOREPLY="${GH_ID}+${GH_USER}@users.noreply.github.com"

# Paths removed from all history (then, where marked, re-added from the current tree).
PURGE=(
  docs/Becker_SARDF517_manual.pdf docs/Becker_SARDF517_manual_akwg.pdf
  docs/GMA1347_C182T_CAP_audio_panel.pdf docs/GMA1347_garmin_audio_panel_guide.pdf
  docs/RT600_CAP_basic_training.pdf docs/RT600_SARDF517_manual.pdf docs/RT600_america_manual.pdf
  docs/TDFM136B_operating.pdf docs/TDFM136_install_operating.pdf
  docs/gma.txt
  docs/figures/b517_p29_bearing_controls-29.png docs/figures/capdeck_p17-17.png
  docs/figures/capdeck_p18-18.png docs/figures/capdeck_p8-08.png docs/figures/capdeck_p9-09.png
  docs/figures/gma1347_panel-04.png docs/figures/gma1347_panel-05.png
  docs/figures/rt600_p08_front_panel-08.png docs/figures/tdfm_p11_front_panel-11.png
  docs/figures/manual/fig_c182t_aircraft.png website/images/fig_c182t_aircraft.png
  docs/mission-base-radio/icut-review.pdf
)
# Generated files whose OLD versions embedded the removed art; the current ones are clean.
READD=(
  docs/CAP_V-SAR_Radio_Features_and_Use_Cases.docx docs/CAP_V-SAR_Radio_Features_and_Use_Cases.pdf
  docs/manual/CAP_VSAR_Flight_Operations_Handbook.pdf
  panels/cap-c182t-mo-station/preview.png
  panels/cap-c182t-mo-station/layouts/e1c8e710-5646-49e1-931f-4aeeb51e4491/preview.png
  panels/cap-c182t-mo-station/layouts/e2c8e710-5646-49e1-931f-4aeeb51e4492/preview.png
)

cat > "$WORK/capsan.py" <<'PY'
"""Shared by the filter-repo callbacks and the re-add step."""
import io, re, zipfile
IP = re.compile(rb"192\.168\.8\.")      # the prefix itself, so prose like "x.x.x.N" cannot slip through
def scrub_bytes(b):
    return IP.sub(rb"192.0.2.", b)
def scrub_zip(data):
    """Rewrite a docx/pptx/xlsx so addresses inside its XML parts are scrubbed."""
    if not data.startswith(b"PK\x03\x04"):
        return data
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return data
    changed, out = False, io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            content = zin.read(info.filename)
            if info.filename.endswith((".xml", ".rels", ".txt", ".json", ".html")) and IP.search(content):
                content, changed = scrub_bytes(content), True
            zout.writestr(info, content, compress_type=info.compress_type)
    return out.getvalue() if changed else data
PY

printf '%s\n' \
  "Ron Craighead <$NOREPLY> <<owner-email-2>>" \
  "Ron Craighead <$NOREPLY> <<owner-email>>" > "$WORK/mailmap"
printf '%s\n' 'regex:192\.168\.8\.==>192.0.2.' > "$WORK/replace-text"

rm -rf "$DEST"
git clone -q --no-local --single-branch --branch main "$SRC" "$DEST"
cd "$DEST"
git remote remove origin

args=(); for p in "${PURGE[@]}" "${READD[@]}"; do args+=(--path "$p"); done
PYTHONPATH="$WORK${PYTHONPATH:+:$PYTHONPATH}" $FILTER --force --invert-paths "${args[@]}" \
  --mailmap "$WORK/mailmap" --replace-text "$WORK/replace-text" \
  --blob-callback 'import capsan; blob.data = capsan.scrub_zip(blob.data)' \
  --message-callback 'import re; message = re.sub(rb"192\.168\.8\.", rb"192.0.2.", message); message = re.sub(rb"<owner-email-2>|<owner-email>", rb"'"$NOREPLY"'", message); return message'

# Re-add the current generated documents and previews in one honest commit.
for f in "${READD[@]}"; do
  mkdir -p "$(dirname "$f")"
  git -C "$SRC" show "HEAD:$f" > "$f"
  PYTHONPATH="$WORK" python3 - "$f" <<'PY'
import sys, capsan
p = sys.argv[1]; d = open(p, "rb").read(); n = capsan.scrub_zip(d)
if n != d: open(p, "wb").write(n)
PY
  git add "$f"
done
GIT_AUTHOR_NAME="Ron Craighead" GIT_AUTHOR_EMAIL="$NOREPLY" GIT_COMMITTER_NAME="Ron Craighead" GIT_COMMITTER_EMAIL="$NOREPLY" \
  git commit -q -m "Add regenerated documents and panel previews

Earlier versions of these generated files embedded third-party artwork and were
removed from history; the current versions are clean. See NOTICE and docs/SOURCES.md."

git reflog expire --expire=now --all && git gc -q --prune=now --aggressive

# ---- verification -------------------------------------------------------------
fail=0
echo "--- 1. purged paths absent from history"
n=$(git log --all --name-only --format= | grep -cE 'RT600_|Becker_SARDF|TDFM136|GMA1347_|gma\.txt|capdeck_|gma1347_panel|icut-review|fig_c182t_aircraft' || true)
[ "$n" = "0" ] || { echo "FAIL: $n purged path mentions in history"; fail=1; }
echo "--- 2. no LAN address left in any commit (text, messages, Word/PowerPoint internals)"
n=$(git log --all -p --no-color --format=%B | grep -ac '192\.168\.8\.' || true)
[ "$n" = "0" ] || { echo "FAIL: $n lines still mention a lab LAN address"; fail=1; }
PYTHONPATH="$WORK" python3 - <<'PY' || fail=1
import subprocess, io, zipfile, re, sys
bad = 0
revs = subprocess.run(["git","rev-list","--all","--objects"],capture_output=True,text=True).stdout.splitlines()
for line in revs:
    sha, _, path = line.partition(" ")
    if not path.endswith((".docx",".pptx",".xlsx")): continue
    data = subprocess.run(["git","cat-file","blob",sha],capture_output=True).stdout
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except Exception: continue
    for n in z.namelist():
        if re.search(rb"192\.168\.8\.", z.read(n)): bad += 1; print("FAIL:", path, n)
sys.exit(1 if bad else 0)
PY
echo "--- 3. no old author or committer email"
n=$(git log --all --format='%ae %ce' | grep -cE 'rpc-cyberflight|gmail' || true)
[ "$n" = "0" ] || { echo "FAIL: $n commits still carry the old emails"; fail=1; }
echo "--- 4. working tree equals the source tree except for the address scrub"
PURGE_LIST="${PURGE[*]}" SRC="$SRC" PYTHONPATH="$WORK" python3 - <<'PY' || fail=1
import os, subprocess, sys, capsan
src = os.environ["SRC"]
a = subprocess.run(["git","-C",src,"ls-tree","-r","--name-only","HEAD"],capture_output=True,text=True).stdout.splitlines()
b = subprocess.run(["git","ls-tree","-r","--name-only","HEAD"],capture_output=True,text=True).stdout.splitlines()
purged = set(os.environ["PURGE_LIST"].split())
missing = sorted(set(a) - set(b)); extra = sorted(set(b) - set(a))
if extra: print("FAIL: files only in the copy:", extra); sys.exit(1)
if sorted(set(missing)-purged): print("FAIL: unexpected files missing:", sorted(set(missing)-purged)); sys.exit(1)
diff = 0
for f in b:
    s = subprocess.run(["git","-C",src,"show","HEAD:"+f],capture_output=True).stdout
    c = open(f,"rb").read()
    want = capsan.scrub_zip(capsan.scrub_bytes(s))
    if c != want and c != capsan.scrub_bytes(s):
        diff += 1; print("FAIL: content differs beyond the address scrub:", f)
sys.exit(1 if diff else 0)
PY
[ "$fail" = "0" ] || { echo "SANITIZE FAILED"; exit 1; }
echo "OK: $(git rev-list --count HEAD) commits, pack $(git count-objects -vH | awk '/size-pack/{print $2,$3}'), identity $NOREPLY"
rm -f "$WORK/capsan.py" "$WORK/mailmap" "$WORK/replace-text"; rmdir "$WORK/__pycache__" 2>/dev/null || true; rmdir "$WORK" 2>/dev/null || true
