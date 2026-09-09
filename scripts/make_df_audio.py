#!/usr/bin/env python3
"""Generate the synthetic receiver audio shipped with both DF heads.

Only Python's standard library is used so the assets are deterministic and can
be rebuilt on any project checkout.  Air Manager 4.2 accepts PCM WAV files.
"""

from __future__ import annotations

import argparse
import io
import math
import random
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RATE = 44_100
TARGETS = (
    ROOT / "instruments/becker-sar-df-517/resources",
    ROOT / "instruments/rhotheta-rt-600/resources",
)


def pcm_wav(samples: list[float]) -> bytes:
    raw = bytearray()
    for sample in samples:
        value = max(-1.0, min(1.0, sample))
        raw.extend(struct.pack("<h", round(value * 32767)))
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(raw)
    return out.getvalue()


def analog_elt(with_doppler_tone: bool) -> bytes:
    """Two seamless seconds of the analog 121.5/243 downward sweep.

    The FAA specifies two to four downward sweeps per second.  Three sweeps per
    second, 1.6 kHz down to 300 Hz, gives the familiar siren-like signal.  The
    DF variant adds the receiver's documented 3 kHz Doppler commutation tone.
    """
    duration = 2.0
    sweep_rate = 3.0
    low_hz, high_hz = 300.0, 1600.0
    rng = random.Random(517 if with_doppler_tone else 600)
    phase = 0.0
    samples: list[float] = []
    for n in range(round(RATE * duration)):
        t = n / RATE
        sweep_phase = (t * sweep_rate) % 1.0
        freq = high_hz - (high_hz - low_hz) * sweep_phase
        phase += 2.0 * math.pi * freq / RATE

        # A short zero-amplitude valley hides the discontinuity where each
        # downward sweep resets to its high frequency.
        edge = min(sweep_phase, 1.0 - sweep_phase)
        envelope = min(1.0, edge / 0.025)
        beacon = (0.72 * math.sin(phase) + 0.13 * math.sin(2.0 * phase))
        radio_noise = 0.025 * rng.uniform(-1.0, 1.0)
        doppler = 0.16 * math.sin(2.0 * math.pi * 3000.0 * t) if with_doppler_tone else 0.0
        samples.append(envelope * (beacon + radio_noise + doppler))
    return pcm_wav(samples)


def digital_406_burst() -> bytes:
    """A 440 ms audible monitor rendition of a 400 bit/s 406 MHz burst."""
    duration = 0.440
    symbol_rate = 400.0
    carrier_hz = 1600.0
    rng = random.Random(406025)
    bits = [1.0 if rng.getrandbits(1) else -1.0
            for _ in range(math.ceil(duration * symbol_rate))]
    samples: list[float] = []
    for n in range(round(RATE * duration)):
        t = n / RATE
        symbol = bits[min(len(bits) - 1, int(t * symbol_rate))]
        ramp = min(1.0, t / 0.006, (duration - t) / 0.006)
        # BPSK phase reversals produce the short, harsh data sound an operator
        # can associate with an arriving Cospas-Sarsat frame.
        value = symbol * math.sin(2.0 * math.pi * carrier_hz * t)
        value += 0.08 * rng.uniform(-1.0, 1.0)
        samples.append(0.78 * max(0.0, ramp) * value)
    return pcm_wav(samples)


def assets() -> dict[str, bytes]:
    return {
        "elt_analog_df.wav": analog_elt(True),
        "elt_analog_clean.wav": analog_elt(False),
        "elt_406_burst.wav": digital_406_burst(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if any checked-in WAV differs from generated audio")
    args = parser.parse_args()
    failed = False
    for target in TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        for name, data in assets().items():
            path = target / name
            if args.check:
                current = path.is_file() and path.read_bytes() == data
                print(f"{'OK' if current else 'STALE'}  {path.relative_to(ROOT)}")
                failed |= not current
            else:
                path.write_bytes(data)
                print(f"wrote {path.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
