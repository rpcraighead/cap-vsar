-- lcd.lua — helpers for drawing the 128x64 monochrome LCD both DF heads use.
--
-- Both the Becker SAR-DF 517 and the RHOTHETA RT-600 use the same panel:
-- "128 x 64 dots, supertwist / transflective, dark blue on yellow-green
-- background" (517 manual §1.3.1, RT-600 manual §2.1). Drawing it on a canvas
-- rather than from photographed artwork keeps the faceplate resolution
-- independent and sidesteps the vendor-likeness question in plan §10.
--
-- Geometry stays in logical LCD coordinates (0..127, 0..63). Text uses
-- antialiased Inconsolata at canvas resolution rather than 3x5 solid blocks.
-- This is a readability treatment, not an exact reproduction of the hardware's
-- undocumented glyph ROM. Fixed cells preserve every page and status field.

lcd = {}
local M = lcd

M.WIDTH  = 128
M.HEIGHT = 64

M.COLOUR_INK = "#1a2560"        -- dark blue

--- Interpolate the backlight colour for a brightness of 0..100.
-- The 517 dims on an exponential curve "allowing very accurate adjusting under
-- night- resp. NVG-conditions" (§3.2.2), so we match that rather than linear.
function M.background_colour(brightness)
    local t = math.max(0, math.min(100, brightness or 100)) / 100
    t = t * t                       -- exponential-ish, matches the real dimming
    local function mix(a, b) return math.floor(a + (b - a) * t + 0.5) end
    return string.format("#%02x%02x%02x",
        mix(0x3f, 0xc6), mix(0x44, 0xd9), mix(0x26, 0x6b))
end

--- Create a drawing context bound to a canvas draw callback.
-- @param scale  canvas pixels per LCD pixel
-- @param ox,oy  canvas offset of LCD pixel (0,0)
function M.context(scale, ox, oy)
    local ctx = { scale = scale, ox = ox or 0, oy = oy or 0 }

    function ctx:x(px) return self.ox + px * self.scale end
    function ctx:y(py) return self.oy + py * self.scale end

    -- -------------------------------------------------------- queued shapes --
    -- These only enqueue; call ctx:fill() or ctx:stroke() to resolve them.

    function ctx:q_rect(px, py, w, h)
        _rect(self:x(px), self:y(py), w * self.scale, h * self.scale)
        return self
    end

    function ctx:q_circle(cx, cy, r)
        _circle(self:x(cx), self:y(cy), r * self.scale)
        return self
    end

    function ctx:q_triangle(x1, y1, x2, y2, x3, y3)
        _triangle(self:x(x1), self:y(y1), self:x(x2), self:y(y2),
                  self:x(x3), self:y(y3))
        return self
    end

    function ctx:q_line(x1, y1, x2, y2)
        _move_to(self:x(x1), self:y(y1))
        _line_to(self:x(x2), self:y(y2))
        return self
    end

    function ctx:fill(colour)
        _fill(colour or M.COLOUR_INK)
    end

    function ctx:stroke(colour, width)
        _stroke(colour or M.COLOUR_INK, (width or 1) * self.scale)
    end

    -- ------------------------------------------------- immediate convenience --

    function ctx:rect(px, py, w, h, colour)
        self:q_rect(px, py, w, h); self:fill(colour)
    end

    function ctx:hline(px, py, len, colour) self:rect(px, py, len, 1, colour) end
    function ctx:vline(px, py, len, colour) self:rect(px, py, 1, len, colour) end

    function ctx:line(x1, y1, x2, y2, colour)
        self:q_line(x1, y1, x2, y2); self:stroke(colour, 1)
    end

    function ctx:circle(cx, cy, r, colour)
        self:q_circle(cx, cy, r); self:stroke(colour, 1)
    end

    function ctx:disc(cx, cy, r, colour)
        self:q_circle(cx, cy, r); self:fill(colour)
    end

    function ctx:triangle(x1, y1, x2, y2, x3, y3, colour)
        self:q_triangle(x1, y1, x2, y2, x3, y3); self:fill(colour)
    end

    function ctx:frame(px, py, w, h, colour)
        self:q_rect(px, py, w, h); self:stroke(colour, 1)
    end

    return ctx
end

-- ---------------------------------------------------------- display text ---

-- Included with AM/AP 3.6 onward; _txt is available from 3.5. Do not use the
-- spacing style (introduced in 5.1); position each glyph explicitly for 4.2.
-- Preview generator uses the same font, em size and ascender offset.
M.FONT_NAME = "inconsolata_bold.ttf"
M.FONT_EM = 5.6
M.FONT_TOP = -1.0

M.CHAR_W    = 3
M.CHAR_H    = 5
M.CHAR_STEP = 4     -- glyph width plus one blank column

--- Width in LCD pixels a string will occupy.
function M.text_width(str)
    if #str == 0 then return 0 end
    return #str * M.CHAR_STEP - 1
end

--- Draw smooth fixed-cell text at logical LCD pixel (px, py).
-- Preserve case: the TDFM's w/n/D modes and x/t/c/m/n/g squelch flags are
-- case-sensitive. Spaces still advance, including padded channel fields.
function M.text(ctx, px, py, str, colour, size_mult)
    local m = size_mult or 1
    local style = string.format("font:%s; size:%.3f; color:%s; halign:center;",
        M.FONT_NAME, M.FONT_EM * ctx.scale * m, colour or M.COLOUR_INK)
    local x = px
    for i = 1, #str do
        local ch = str:sub(i, i)
        if ch ~= " " then
            _txt(ch, style, ctx:x(x + M.CHAR_W * m / 2),
                 ctx:y(py + M.FONT_TOP * m))
        end
        x = x + M.CHAR_STEP * m
    end
    return x
end

--- Right-aligned text ending at LCD pixel px.
function M.text_right(ctx, px, py, str, colour, size_mult)
    local m = size_mult or 1
    return M.text(ctx, px - M.text_width(str) * m, py, str, colour, m)
end

--- Convert a bearing in degrees to a point on a circle, 0 deg at the top and
--- increasing clockwise — how a relative-bearing display works.
function M.polar(cx, cy, radius, degrees)
    local rad = math.rad(degrees - 90)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad)
end

return M
