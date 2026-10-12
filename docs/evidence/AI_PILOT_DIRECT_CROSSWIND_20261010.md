# KMYF 28R direct-crosswind landing trials

2026-10-10 PDT. Branch `feat/ai-pilot-direct-crosswind`. Attended X-Plane 12
engineering trials with the stock C172SP G1000. The configured wind was 15 kt
from 90° left or right of runway heading; X-Plane measured about 10.5 kt near
touchdown because it attenuates surface wind. These results do not qualify
real-world or unattended flight.

The unflared 3° glidepath now intersects 25 ft beyond KMYF 28R's 366 m
displaced threshold, at 373.62 m from the physical runway end. The independent
observer requires touchdown between that point and 400 ft farther along,
within 4 m of centerline, 5–7° nose-up before contact, runway-heading
alignment, and controlled moderate-brake rollout to a complete stop. The
controller aims for 65 KIAS, uses staged 10°/20°/30° flaps, keeps windward
aileron and runway-alignment rudder through contact, and increases windward
aileron as rollout speed falls.

| Campaign | Scored outcome |
| --- | --- |
| First alternating left/right sequence | Six consecutive passes; seventh attempt interrupted by the simulator bridge before touchdown, so it was not a scored landing. |
| Sound-enabled alternating sequence | First attempt ended before touchdown during startup. The next completed right-crosswind landing missed the 5° rollout-heading limit by 0.045°. The following eight completed landings, alternating left/right, all passed. |

The two machine-readable ledgers are
`/home/ron/.cache/capvsar/ai-pilot/kmyf-direct15-gate-a-20261010-ledger.json`
and
`/home/ron/.cache/capvsar/ai-pilot/kmyf-direct15-gate-b-sound-20261010-ledger.json`.
They contain the predeclared wind plan, per-trial results, raw JSONL trace
paths and SHA-256 hashes. Both record controller source SHA-256
`5778c01b7e98181c3556eab0b7b467e63fc17e5c6b12700020b2459dd1bda966`.
The unflown experimental change that raised ground rudder authority to 0.70
was reverted so the saved controller matches the flown source.

The requested strict consistency gate was not completed: a simulator-bridge
interruption broke the first sequence, and the sound-enabled sequence includes
one scored rollout failure before the eight-pass streak. The randomized ±90°
crosswind campaign was not started. The user stopped the trials. No KRNM taxi
or takeoff trials were started in this session.

X-Plane was closed afterward. Original simulator preferences, stock C172
preferences and scenery configuration were restored byte-for-byte from
`/home/ron/X-Plane 12/Output/capvsar-backups/ai-pilot-direct-crosswind-20261010/`.
The temporary bridge plugin files and socket were removed.
