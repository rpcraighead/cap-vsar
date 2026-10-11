#!/usr/bin/env python3
"""Fetch the pinned GPL FlightGear C182 donor used by the local prototype.

The donor is deliberately kept outside this Apache-2.0 repository.  This
script downloads one reviewed Git revision, verifies its archive checksum,
and extracts it into a caller-selected cache directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


DONOR_REPOSITORY = "https://github.com/HHS81/c182s"
DONOR_COMMIT = "1359d63393c7fc9145953b081d151d93627e791a"
DONOR_ARCHIVE_URL = f"{DONOR_REPOSITORY}/archive/{DONOR_COMMIT}.tar.gz"
DONOR_ARCHIVE_SHA256 = (
    "d81628fff8489af41d312c0e0bc14e1de2ac10a50d6c0c75f937441f81343fbe"
)
CACHE_ROOT = Path.home() / ".cache" / "capvsar"
DEFAULT_DONOR = CACHE_ROOT / "capvsar-flightgear-c182-pinned"
DEFAULT_ARCHIVE = CACHE_ROOT / "hhs81-c182s-1359d633.tar.gz"
REQUIRED_FILE_SHA256 = {
    "LICENSE": "8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643",
    "Models/c182s.ac": "9324ba50bf9eb8e2e7215a4b1f5a44b8da2ec782c913d557d70df922daf0f436",
    "Models/c182t.xml": "7c48e14a904a05030a06e8b4c699565f3c9fe10754ac69d018e9f37a5b40718d",
    "Models/Liveries/Default.png": "ef329278ea11a23b03da789f4338b0e4316fff1d63335be3b0c45a8b96fcd783",
    "Models/Lights.png": "753c7905ac38eda3a8203ece494aae6be706c5d8b950f7a5da0812a97c38a208",
    "Models/PropBlur.png": "b213b013fb4237842bcbc949f3f1998c947f466af6f2da62150848eff666bc72",
    # The editable source of Models/c182s.ac - 88 objects matching it 1:1, and
    # the file any exterior geometry correction actually edits. It was the one
    # unpinned asset in an otherwise checksum-verified pipeline.
    "dev/C182S.blend": "3bfe0720204a35c145d5247b2bcfd5aac1785257e2b98be48bbb8e62a9a7ae58",
    # The donor's cockpit/interior model. Pinned for provenance; it holds no
    # airframe geometry and is not the source for exterior work.
    "dev/C182T.blend": "64ceac4b3643a96c2af41b9983f5eedbad32778da108f53556288d3fe740bca3",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_donor(directory: Path) -> None:
    missing = [
        name for name in REQUIRED_FILE_SHA256 if not (directory / name).is_file()
    ]
    if missing:
        raise ValueError(
            f"FlightGear donor at {directory} is incomplete; missing: "
            + ", ".join(missing)
        )
    license_head = (directory / "LICENSE").read_text(errors="replace")[:200]
    if "GNU GENERAL PUBLIC LICENSE" not in license_head:
        raise ValueError(f"Unexpected donor license in {directory / 'LICENSE'}")
    changed = [
        name
        for name, expected in REQUIRED_FILE_SHA256.items()
        if sha256(directory / name) != expected
    ]
    if changed:
        raise ValueError(
            "FlightGear donor files differ from the pinned commit: "
            + ", ".join(changed)
        )


def _extract_archive(archive: Path, destination: Path) -> None:
    """Extract an archive without permitting links or path traversal."""
    with tempfile.TemporaryDirectory(prefix="capvsar-c182-donor-") as temp_name:
        temp = Path(temp_name)
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            if any(member.issym() or member.islnk() for member in members):
                raise ValueError("Donor archive contains links; refusing extraction")
            tar.extractall(temp, filter="data")

        roots = [entry for entry in temp.iterdir() if entry.is_dir()]
        if len(roots) != 1:
            raise ValueError("Donor archive does not have one top-level directory")
        validate_donor(roots[0])

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(roots[0]), destination)


DOWNLOAD_TIMEOUT_S = 60


def _download(url: str, destination: Path, timeout: float = DOWNLOAD_TIMEOUT_S) -> None:
    """Fetch url into destination, giving up if the server goes quiet.

    urlretrieve has no timeout, so a stalled connection hung the build with no
    output. `timeout` bounds each socket operation, not the whole transfer, so a
    slow 120 MB download that keeps moving is fine.
    """
    with urllib.request.urlopen(url, timeout=timeout) as response, \
            destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def fetch_donor(
    destination: Path,
    *,
    archive: Path | None = None,
    force: bool = False,
) -> Path:
    destination = destination.expanduser().resolve()
    if destination.exists() and not force:
        try:
            validate_donor(destination)
        except ValueError as error:
            raise ValueError(
                f"{error}. Re-run with --force to replace it with a fresh, "
                f"checksum-verified copy."
            ) from error
        return destination

    with tempfile.TemporaryDirectory(prefix="capvsar-c182-download-") as temp_name:
        downloaded = Path(temp_name) / "flightgear-c182.tar.gz"
        if archive is None:
            if DEFAULT_ARCHIVE.exists():
                shutil.copy2(DEFAULT_ARCHIVE, downloaded)
            else:
                print(f"[*] Downloading {DONOR_ARCHIVE_URL}")
                _download(DONOR_ARCHIVE_URL, downloaded)
        else:
            shutil.copy2(archive, downloaded)

        actual = sha256(downloaded)
        if actual != DONOR_ARCHIVE_SHA256:
            raise ValueError(
                "FlightGear donor archive checksum mismatch: "
                f"expected {DONOR_ARCHIVE_SHA256}, got {actual}"
            )
        _extract_archive(downloaded, destination)
        if archive is None:
            DEFAULT_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(downloaded, DEFAULT_ARCHIVE)

    metadata = {
        "repository": DONOR_REPOSITORY,
        "commit": DONOR_COMMIT,
        "archive_url": DONOR_ARCHIVE_URL,
        "archive_sha256": DONOR_ARCHIVE_SHA256,
        "license": "GPL-2.0 (GitHub classification and upstream root license text)",
    }
    (destination / ".capvsar-donor.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    validate_donor(destination)
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", default=DEFAULT_DONOR, type=Path,
                        help="cache directory (default: ~/.cache/capvsar/capvsar-flightgear-c182-pinned)")
    parser.add_argument(
        "--archive",
        type=Path,
        help="use an already-downloaded archive (still checksum-verified)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing destination after the archive verifies",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    destination = fetch_donor(
        args.destination, archive=args.archive, force=args.force
    )
    print(f"[+] Pinned FlightGear C182 donor ready: {destination}")
    print(f"[+] Commit: {DONOR_COMMIT}")
    print(f"[+] Archive SHA-256: {DONOR_ARCHIVE_SHA256}")


if __name__ == "__main__":
    main()
