-- cap_df_audio.lua — Air Manager 4.2 receiver-audio state machine.
--
-- The X-Plane propagation plugin owns RF reception and publishes rx_open and signal.
-- This module owns the sound produced by the DF head's audio output, including
-- realistic RF signal-to-noise (SNR) degradation.
-- Air Manager's sound API is intentionally kept here so logic.lua can describe
-- the receiver state without knowing which WAV is currently playing.

cap_df_audio = {}
local M = cap_df_audio

local sounds = {
    analog_df    = sound_add("elt_analog_df.wav", 0),
    analog_clean = sound_add("elt_analog_clean.wav", 0),
    burst_406    = sound_add("elt_406_burst.wav", 0),
    noise        = sound_add("elt_noise.wav", 0),
}

local playing = nil

local function stop_current()
    if playing then sound_stop(sounds[playing]) end
    if sounds.noise then sound_stop(sounds.noise) end
    playing = nil
end

--- Synchronize audio with instantaneous receiver truth.
-- ready: power-up/self-test has finished
-- rx_open: squelch is open right now (never TIMEHOLD)
-- band_mhz: receiver's effective frequency, including scan dwell
-- volume: front-panel volume, normalized to 0..1
-- suppress_doppler: Becker STORE removes the 3 kHz DF tone on AM
-- signal: RF signal strength normalized 0..1 (from cap/df/signal)
function M.update(ready, rx_open, band_mhz, volume, suppress_doppler, signal)
    local gain = math.max(0, math.min(1, volume or 0))
    if not ready or not rx_open or gain <= 0 then
        stop_current()
        return
    end

    local sig = signal
    if sig == nil and cap_df and cap_df.state and cap_df.state.signal then
        sig = cap_df.state.signal / 100
    end
    sig = math.max(0, math.min(1, sig or 1.0))

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

    -- Real DF receivers bury the sweep in hiss as signal degrades with range or terrain.
    local tone_gain = gain * math.max(0.15, sig)
    local noise_gain = gain * math.max(0, (1.0 - sig) * 0.75)

    if playing ~= wanted then
        stop_current()
        sound_volume(sounds[wanted], tone_gain)
        sound_volume(sounds.noise, noise_gain)
        -- volume knob drives receiver gain: sound_volume(sounds[wanted], gain)
        if wanted == "burst_406" then
            -- The engine closes rx_open after the real 440 ms transmit window;
            -- play once so a delayed callback cannot accidentally repeat it.
            sound_play(sounds[wanted])
        else
            sound_loop(sounds[wanted])
        end
        if noise_gain > 0.01 then
            sound_loop(sounds.noise)
        end
        playing = wanted
    else
        sound_volume(sounds[wanted], tone_gain)
        sound_volume(sounds.noise, noise_gain)
        -- volume knob drives receiver gain: sound_volume(sounds[wanted], gain)
        if noise_gain > 0.01 then
            sound_loop(sounds.noise)
        else
            sound_stop(sounds.noise)
        end
    end
end

function M.stop()
    stop_current()
end
