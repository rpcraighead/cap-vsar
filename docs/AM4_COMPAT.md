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
