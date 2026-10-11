# Air Manager 4 compatibility constraint

Spare Air Manager 4 licences exist, so the DF heads and the MO COM panel are
built against the **AM4-compatible API subset**. An instrument written this way
opens in Air Manager 5; the reverse is not reliable. Building to AM4 therefore
costs nothing and keeps the spare licences useful.

## X-Plane 12 support comes from the plugin, not from Air Manager

Air Manager talks to the simulator through a separately-versioned **flightsim
plugin**. Its release notes record:

- **v4.0** - "X-plane 12 added"
- v4.3 - more reliable protocol between the simulator and Air Manager *or Air Player*
- v4.4 - support for the Steam version of X-Plane on Linux
- current: v4.5.3

The plugin is one download serving both the AM4 and AM5 lineages, and nothing
in its notes marks any release as Air Manager 5 only. So AM4 plus a current
plugin is expected to work against X-Plane 12.

**This is inference, not a vendor statement.** Sim Innovations does not publish
an explicit "Air Manager 4 supports X-Plane 12" line. Verify on the laptop
before relying on it - install AM4, install the current flightsim plugin, and
confirm a stock dataref such as `sim/flightmodel/position/psi` moves.

## APIs we may use

All long-standing, present well before AM4:

`img_add` `txt_add` `dial_add` `button_add` `switch_add` `slider_add`
`running_img_add_*` `running_txt_add_*` `canvas_add` `group_add`
`xpl_dataref_subscribe` `xpl_dataref_write` `xpl_command` `xpl_command_subscribe`
`xpl_connected` `timer_start` `sound_play` `user_prop_*` `hw_*`

## APIs we must NOT use

These arrived in Air Manager 5 and would silently break an AM4 station:

| API | Added |
|---|---|
| `layer_add`, `layer_mouse_cursor` | V5.0 / V5.1 |
| `scene_add` (3D objects) | V5.0 |
| `_solid` / `_hole` shape functions, `viewport_shape` | V5.2 |

`video_stream_add` arrived in V4.2, so it is supported on Air Manager 4.2+
(used by the G1000 MFD video stream and watchdog recovery wrapper for X-Plane 12),
but not on earlier 4.x releases.

## What the offline test harness refuses (D3)

`tests/am.py` is built from the signature table in `tests/am_api.py`, which is
taken from the AM 4.2 code snippets and the stock Sim Innovations G1000
instrument, and it refuses what Air Manager refuses. Things instruments have got
wrong before, now errors offline:

- **`dial_add` has one callback.** `dial_add(img, x, y, w, h, [step], turn_cb)`;
  `turn_cb(direction)` is called with +1 or -1. There is no press or release
  callback (Lua silently ignored the extra arguments). A knob that is also a push
  switch is a transparent `button_add(nil, nil, x, y, w, h, press_cb, [release_cb])`
  over the knob centre, added **after** the dial. Use `knob_push(spec, press,
  release)` from `_shared/lib/knob_push.lua` (copied into each instrument's
  `lib/` by `scripts/deploy_df_instruments.py`). The stock G1000 does the same
  with a 40x40 button on a 100x100 knob; the helper uses half the knob, at least
  24 units.
- **Names must exist in X-Plane.** `xpl_dataref_subscribe`, `xpl_dataref_write`
  and `xpl_command` only accept names in `tests/fixtures/xplane_names.json`
  (types included; a write needs a writable dataref) or the `cap/df/*` names
  `PI_capvsar_df.py` registers. After adding a name to an instrument run
  `scripts/check_xplane_names.py`: it verifies every `sim/...` literal in the
  Lua against `X-Plane 12/Resources/plugins/DataRefs.txt` and `Commands.txt`
  and regenerates the fixture. Laminar's files are never committed.
- **A multi-dataref `xpl_dataref_subscribe`** is one callback that receives every
  value, whenever any of them changes: `(name, type, name, type, ..., callback)`.
- **Colours** are a name, `#RGB`, `#RRGGBB` or `#RRGGBBAA`. The CSS `rgba(...)`
  form is rejected.
- **`video_stream_add` stacks a new node above everything added before it** and
  there is no call to remove one. Create one node, below any overlay, and re-arm
  it by hiding and showing it (`g1000-mfd-watchdog`).
- **`timer_start`** is `(delay, interval, cb)` with either number nil, or
  `(delay, cb)`.
- **No `require`, `dofile`, `loadfile`, `package` or `io`** in the sandbox.
- A function that is not in the table does not exist. Add it to `tests/am_api.py`
  (with its signature from a snippet) the first time an instrument needs it.

Assumptions the harness makes that need a look at the live application, because
no snippet or log settles them: that a turn aimed at the middle of a knob still
reaches the dial under a `knob_push` button (the stock G1000 relies on it); that
hide-then-show re-links a video stream; that `#RRGGBBAA` is accepted by `_fill`;
and that `sound_add(file, volume)` takes the optional volume (the snippet shows
one argument; the DF heads have always passed two and the log shows no error).

## Licensing note

An Air Manager licence is not an Air Player licence. Crew stations that only
display panels - the Mission Observer and Scanner positions in Mode B - need
**Air Player** seats, which are sold separately. Spare AM4 licences cover
instrument development and the pilot station, not the extra crew displays.

## Custom datarefs

The DF heads subscribe to `cap/df/*`, which our XPPython3 plugin registers at
`XPluginStart`. They therefore exist before Air Manager connects, which is the
condition that matters. Types are int/float/double - all ordinary. No reason
this differs between AM4 and AM5, but it is worth being the first thing tested
once a station is up.
