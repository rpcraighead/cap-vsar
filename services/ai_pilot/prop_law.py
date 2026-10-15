"""Constant-speed propeller lever schedule for the AI pilot controllers.

The C172 package has a fixed-pitch prop, so its frames carry no prop channel.
The CAP 487 C182T has a governed prop (ACF `_prop_type` 1) and its bridge takes
a `prop` lever (`sim/cockpit2/engine/actuators/prop_ratio`, 1.0 = governor at
redline RPM) as part of every atomic frame.

The schedule is the one a pilot flies: lever full forward for takeoff, climb,
approach and any go-around, and the profile's cruise setting only once
established in level cruise. It is derived from the snapshot, not from a
controller's stage, so every controller (takeoff, taxi, mission, pattern,
landing) applies the same rule. Lever moves are rate-limited so a change never
steps the governor, and the cruise setting has hysteresis so a ragged altitude
hold cannot make it chatter.
"""
from __future__ import annotations

from dataclasses import replace

from .aircraft_profiles import AircraftProfile

FULL = 1.0
SLEW_PER_S = .25          # lever travel per second of simulated time
CRUISE_MIN_AGL_FT = 1000.
CRUISE_MIN_KIAS = 85.
LEVEL_ENTER_FPM = 300.    # |vvi| below this, held, to enter cruise
LEVEL_EXIT_FPM = 500.     # |vvi| above this to leave it


class PropLaw:
    def __init__(self, profile: AircraftProfile, initial: float = FULL):
        self.profile = profile
        self.enabled = profile.constant_speed_prop
        self.ratio = initial
        self.cruise = False
        self._last_sim = None

    def target(self, v, allow_cruise: bool = True) -> float:
        cruise = self.profile.prop_cruise_ratio
        if cruise >= FULL or not allow_cruise:
            self.cruise = False
            return FULL
        in_cruise_air = (not v["on_ground"]
                         and v["agl_m"] / .3048 > CRUISE_MIN_AGL_FT
                         and v["kias"] >= CRUISE_MIN_KIAS
                         and v["flap_actual"] < .02)
        limit = LEVEL_EXIT_FPM if self.cruise else LEVEL_ENTER_FPM
        self.cruise = in_cruise_air and abs(v["vvi_fpm"]) < limit
        return cruise if self.cruise else FULL

    def step(self, v, allow_cruise: bool = True) -> float:
        """Lever command for this snapshot (`v` is `snapshot["values"]`).
        `allow_cruise` False holds the lever full forward whatever the state."""
        goal = self.target(v, allow_cruise)
        sim = v["sim_time_s"]
        dt = 0. if self._last_sim is None else min(max(sim - self._last_sim, 0.), .25)
        self._last_sim = sim
        step = SLEW_PER_S * dt
        self.ratio += max(-step, min(step, goal - self.ratio))
        return self.ratio

    def add_to(self, frame: dict, v, allow_cruise: bool = True) -> dict:
        """`frame` plus a `prop` entry, only for a governed-prop profile."""
        if self.enabled:
            frame["prop"] = self.step(v, allow_cruise)
        return frame


def full_forward(step):
    """Decorate a guidance `step` that returns a command dataclass with a `prop`
    field: a governed-prop profile flies the lever full forward on the ground,
    on the runway and in the climb-out (the cruise schedule is PropLaw's)."""
    def wrapper(self, *args, **kwargs):
        command = step(self, *args, **kwargs)
        return replace(command, prop=FULL) if self.profile.constant_speed_prop else command
    wrapper.__name__, wrapper.__doc__ = step.__name__, step.__doc__
    return wrapper
