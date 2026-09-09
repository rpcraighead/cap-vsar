#!/usr/bin/env python3
"""
Deploy the CAP Cessna 182T Mission Observer (MO) panel to Air Manager.

Usage:
  python3 scripts/deploy_mo_panel.py                  # Deploys to local Air Manager
  python3 scripts/deploy_mo_panel.py --target <path>  # Deploys to a custom Air Manager directory
  python3 scripts/deploy_mo_panel.py --zip            # Creates cap-c182t-mo-station.zip for transfer
"""

import os
import sys
import shutil
import argparse
import subprocess

PANEL_UUID = "a4c8e710-5646-49e1-931f-4aeeb51e4490"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(REPO_ROOT, "panels", "cap-c182t-mo-station")

DEFAULT_DEST = os.path.expanduser(f"~/Air Manager/panels/OPEN_DIRECTORY/{PANEL_UUID}")
ALT_LINUX_DEST = os.path.expanduser(f"~/.local/share/sim_innovations/Air Manager/panels/OPEN_DIRECTORY/{PANEL_UUID}")

def deploy(dest_dir, regenerate=False):
    if regenerate:
        gen_script = os.path.join(SOURCE_DIR, "generate_assets.py")
        print(f"[*] Regenerating background and preview images via {gen_script}...")
        subprocess.check_call([sys.executable, gen_script])

    print(f"[*] Deploying MO Panel dataset:")
    print(f"    Source: {SOURCE_DIR}")
    print(f"    Target: {dest_dir}")

    os.makedirs(dest_dir, exist_ok=True)

    # Copy files
    for root, dirs, files in os.walk(SOURCE_DIR):
        rel_path = os.path.relpath(root, SOURCE_DIR)
        target_root = dest_dir if rel_path == "." else os.path.join(dest_dir, rel_path)
        os.makedirs(target_root, exist_ok=True)
        for f in files:
            src_file = os.path.join(root, f)
            dst_file = os.path.join(target_root, f)
            shutil.copy2(src_file, dst_file)

    print("[+] File deployment complete!")
    reg_script = os.path.join(REPO_ROOT, "scripts", "register_mo_panel.py")
    if os.path.exists(reg_script):
        print("[*] Registering panel in Air Manager config.sqlite3...")
        subprocess.call([sys.executable, reg_script])

def make_zip():
    zip_path = os.path.join(REPO_ROOT, "cap-c182t-mo-station.zip")
    print(f"[*] Packaging panel for external deployment to: {zip_path}")
    shutil.make_archive(
        base_name=os.path.splitext(zip_path)[0],
        format="zip",
        root_dir=os.path.dirname(SOURCE_DIR),
        base_dir="cap-c182t-mo-station"
    )
    print(f"[+] Archive created successfully at {zip_path}")
    print(f"    Extract this zip to ~/Air Manager/panels/OPEN_DIRECTORY/{PANEL_UUID} on any PC.")

def main():
    parser = argparse.ArgumentParser(description="Deploy CAP C182T MO Panel to Air Manager")
    parser.add_argument("--target", help="Destination directory (defaults to ~/Air Manager/panels/OPEN_DIRECTORY/<UUID>)")
    parser.add_argument("--regenerate", action="store_true", help="Re-run asset generator before deploying")
    parser.add_argument("--zip", action="store_true", help="Package panel into a transferrable ZIP file")

    args = parser.parse_args()

    if args.zip:
        make_zip()
        return

    dest = args.target or (DEFAULT_DEST if os.path.exists(os.path.dirname(os.path.dirname(DEFAULT_DEST))) else ALT_LINUX_DEST)
    deploy(dest, regenerate=args.regenerate)

if __name__ == "__main__":
    main()

