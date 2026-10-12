#!/usr/bin/env python3
"""Create an isolated CAP 487 ACF for a single fuselage-drag experiment.

This does not change the package builder or an installed aircraft. The output
is an explicitly experimental ACF to put in a separate, local test package.
Only the named fuselage drag record may differ from the input ACF.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path


RECORD = "P _body/0/_part_cd "
IDENTITY = "P acf/_tailnum CAP 487"
# The baseline is whatever the builder writes (0.120 since the 2026-10-11
# calibration; it was the C172's 0.200000003 before).
STOCK_CD = 0.12


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_candidate(source: Path, output: Path, body_cd: float) -> dict:
    """Write exactly one ACF record, refusing ambiguous or stale input."""
    source = source.expanduser().resolve(strict=True)
    output = output.expanduser()
    resolved_output = output.resolve()
    if source == resolved_output:
        raise ValueError("Output must differ from the source ACF")
    if output.exists() or output.is_symlink():
        raise ValueError(f"Output already exists: {output}")
    output = resolved_output
    if not math.isfinite(body_cd) or not 0.025 <= body_cd <= 0.25:
        raise ValueError("Experimental body Cd must be finite and between 0.025 and 0.250")

    original = source.read_bytes()
    lines = original.decode("utf-8").splitlines(keepends=True)
    if sum(line.rstrip("\r\n") == IDENTITY for line in lines) != 1:
        raise ValueError("Input must identify the generated CAP 487 aircraft exactly once")
    matches = [i for i, line in enumerate(lines) if line.startswith(RECORD)]
    if len(matches) != 1:
        raise ValueError("Expected exactly one fuselage drag record")
    old = lines[matches[0]]
    if not math.isclose(float(old[len(RECORD):].strip()), STOCK_CD, abs_tol=1e-8):
        raise ValueError("Input is not the builder's calibrated 0.120 fuselage baseline")
    newline = "\r\n" if old.endswith("\r\n") else "\n"
    lines[matches[0]] = f"{RECORD}{body_cd:.9f}{newline}"
    candidate = "".join(lines).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    return {
        "source": str(source), "output": str(output),
        "source_sha256": sha256(original), "candidate_sha256": sha256(candidate),
        "changed_record": RECORD.strip(), "from": STOCK_CD, "to": body_cd,
        "status": "experimental; no flight-model validation",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acf", type=Path, required=True, help="baseline CAP 487 ACF")
    parser.add_argument("--output", type=Path, required=True, help="new, separate ACF path")
    parser.add_argument("--body-cd", type=float, required=True,
                        help="experimental fuselage Cd (0.025 through 0.200)")
    args = parser.parse_args()
    result = make_candidate(args.acf, args.output, args.body_cd)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
