-- knob_push.lua — the push action of a rotary knob.
--
-- Air Manager 4.2's dial_add(img, x, y, w, h, [step], turn_callback) takes ONE
-- callback, the turn, called with +1 or -1. It has no press or release. A dial
-- that is also a push switch is a dial with a transparent button laid over its
-- centre: the stock Sim Innovations G1000 does exactly that for every knob,
-- button_add(nil, nil, x, y, 40, 40, push_callback) added right after the
-- dial_add (see the CRS/HDG/NAV/COM/FMS rotaries in its logic.lua).
--
-- The button is smaller than the knob and sits on its centre, so a turn aimed at
-- the rim still lands on the dial. Call this immediately AFTER the dial_add it
-- belongs to: Air Manager stacks controls in the order they are added, and a
-- button added first would sit under the dial and never be hit.
--
-- @param spec     the knob's geometry table, { x =, y =, w =, h = }
-- @param press    called when the button goes down
-- @param release  called when it comes up (optional)
-- @return the button id
function knob_push(spec, press, release)
    local side = math.max(24, math.floor(math.min(spec.w, spec.h) * 0.5))
    local x = math.floor(spec.x + (spec.w - side) / 2)
    local y = math.floor(spec.y + (spec.h - side) / 2)
    return button_add(nil, nil, x, y, side, side, press, release)
end
