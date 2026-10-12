> **Historical.** This is the Phase 0/1 bring-up note and several things in it
> are out of date (it still says to edit `CONSOLE` and `CALLSIGN` at the top of
> the plugin; they now come from `capvsar_station.ini`, built by
> `scripts/build_station_kit.py`, and the default console is the TLS front door
> `https://192.0.2.151`). Current references: `docs/DATAREF_CONTRACT.md` (the
> datarefs and how the engine behaves), `docs/CONNECT.md` (station setup) and
> the header of `xplane/PI_capvsar_df.py`.

# Phase 0/1 - DF engine plugin

`PI_capvsar_df.py` is the propagation engine. It runs inside X-Plane because
two things it must do are only possible there: probing real terrain for line of
sight, and reading aircraft state at frame rate.

## Installed on the workstation

```
/home/ron/X-Plane 12/Resources/plugins/XPPython3/          v4.7.1, bundles Python 3.12
/home/ron/X-Plane 12/Resources/plugins/PythonPlugins/PI_capvsar_df.py
```

XPPython3 ships its own interpreter, so the system Python 3.14 is irrelevant.

## Datarefs published

Air Manager subscribes to these exactly as it would to a stock dataref.

| Dataref | Type | Meaning |
|---|---|---|
| `cap/df/valid` | int | 1 when a usable bearing exists |
| `cap/df/bearing_rel` | float | degrees relative to the nose - drives the needle |
| `cap/df/bearing_true` | float | degrees true |
| `cap/df/signal` | float | 0..1 - drives the signal bar |
| `cap/df/distance_nm` | float | slant range, for the instructor |
| `cap/df/in_cone` | int | inside the cone of confusion |
| `cap/df/blocked` | int | terrain is masking the signal |
| `cap/df/band` | float | 121.5 / 243 / 406 |
| `cap/scenario/active` | int | a sortie is running |
| `cap/scenario/beacon_lat` | double | writable, for offline testing |
| `cap/scenario/beacon_lon` | double | writable |
| `cap/scenario/beacon_elev` | float | writable, feet MSL |

## Terrain masking - why this lives in the sim

`line_of_sight_blocked()` samples 24 points along the path, probes terrain at
each, and compares ground elevation against the straight ray from beacon to
aircraft. If ground rises more than 50 ft above the ray, the signal is
attenuated to 6% rather than silenced - a masked beacon fades, it does not
vanish cleanly.

No server-side model can do this. It is the single reason the plan puts the
engine here rather than in Air Manager or in the exercise console.

Outside loaded scenery the probe misses and the path is assumed clear. That is
the safe failure: it never invents a ridge that is not there.

## It is also the sim bridge

The plan sketched a separate bridge process. It is not needed. A background
thread in the plugin polls the exercise console for beacon truth and effect
switches, and reports position back to `POST /api/positions` every 2 s. No
network call ever runs in the flight loop.

Console unreachable is not an error - the plugin keeps running on the last
scenario it received, or on whatever was written into the writable datarefs.

Edit `CONSOLE` and `CALLSIGN` at the top of the plugin per station.

## Validation

Geodesy checked against the FAA plate for the KCRQ ILS:

| Check | Computed | Reference | Delta |
|---|---|---|---|
| KCRQ to ESCON bearing | 76.01 T | 065 mag + ~11E var = ~076 T | 0.01 deg |
| KCRQ to ESCON distance | 10.40 nm | plate: I-CRQ 10.4 DME | 0.00 nm |
| Cardinal bearings from KCRQ | 0.00 / 89.67 / 180.00 / 270.33 | 0 / 90 / 180 / 270 | < 0.33 deg |
| Reciprocal consistency | 256.12 vs 256.01 | great-circle convergence | 0.11 deg |
| One degree of latitude | 60.04 nm | 60.00 nm | 0.04 nm |

The sub-degree cardinal errors are great-circle convergence at 33N, which is
correct behaviour rather than error.

**Phase 1 exit criterion - bearings correct within one degree - is met for the
geodesy.** The terrain-masking half of that criterion is untested: it needs
X-Plane running, which needs a display session on the workstation.

## What is still missing

- **Air Manager is not installed.** It is licensed software. Until it is, the
  Phase 0 exit criterion - a value from our plugin visibly moving a needle -
  cannot be demonstrated. Everything on the sim side of that boundary is ready.
- The plugin has never been loaded by X-Plane. It parses under the bundled
  3.12 and the API calls are written against the shipped `.pyi` stubs, but
  first load will still be first load.
