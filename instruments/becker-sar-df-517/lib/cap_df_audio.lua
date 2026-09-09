-- cap_df_audio.lua — Air Manager 4.2 receiver-audio state machine.
--
-- The X-Plane propagation plugin owns RF reception and publishes rx_open.
-- This module owns only the sound produced by the DF head's audio output.
-- Air Manager's sound API is intentionally kept here so logic.lua can describe
-- the receiver state without knowing which WAV is currently playing.

cap_df_audio = {}
local M = cap_df_audio

local sounds = {
    analog_df    = sound_add("elt_analog_df.wav", 0),
    analog_clean = sound_add("elt_analog_clean.wav", 0),
    burst_406    = sound_add("elt_406_burst.wav", 0),
}

local playing = nil

local function stop_current()
    if playing then sound_stop(sounds[playing]) end
    playing = nil
end

--- Synchronize audio with instantaneous receiver truth.
-- ready: power-up/self-test has finished
-- rx_open: squelch is open right now (never TIMEHOLD)
-- band_mhz: receiver's effective frequency, including scan dwell
-- volume: front-panel volume, normalized to 0..1
-- suppress_doppler: Becker STORE removes the 3 kHz DF tone on AM
function M.update(ready, rx_open, band_mhz, volume, suppress_doppler)
    local gain = math.max(0, math.min(1, volume or 0))
    if not ready or not rx_open or gain <= 0 then
        stop_current()
        return
    end

    local band = band_mhz or 0
    local wanted
    if band >= 400 then
        wanted = "burst_406"
    elseif suppress_doppler or (band >= 154 and band <= 163) then
        -- STORE leaves the received modulation audible while removing only the
        -- 3 kHz Doppler tone. Marine-band FM is filtered the same way.
        wanted = "analog_clean"
    else
        wanted = "analog_df"
    end

    if playing ~= wanted then
        stop_current()
        sound_volume(sounds[wanted], gain)
        if wanted == "burst_406" then
            -- The engine closes rx_open after the real 440 ms transmit window;
            -- play once so a delayed callback cannot accidentally repeat it.
            sound_play(sounds[wanted])
        else
            sound_loop(sounds[wanted])
        end
        playing = wanted
    else
        sound_volume(sounds[wanted], gain)
    end
end

function M.stop()
    stop_current()
end
