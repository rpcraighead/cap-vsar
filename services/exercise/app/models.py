"""
Request bodies, in one place (C15-1).

X-6 is why these matter: two endpoints took raw dicts, and one of them wrote
whatever it was handed into the scenario definition. Every body the console
accepts is a model now, and they are together so the accepted shape of the
API can be read in one sitting.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from .settings import DEFAULT_EFFECTS

# FE-8: Pydantic v2 accepts NaN and Infinity for a float by default, and
# Starlette's JSON parser accepts the bare `NaN` literal, so a client could put
# a NaN bearing in the database - where SQLite stores it as NULL, and base.js
# then throws on `b.bearing_true.toFixed(0)` for every reconnect that replays
# it, killing the bearing log for the rest of the sortie. Every model here
# refuses non-finite floats.
NO_NAN = {"allow_inf_nan": False}


class ScenarioIn(BaseModel):
    model_config = NO_NAN

    # X-6: nothing checked these, so a transposed pair (33.1, -117.2 entered as
    # -117.2, 33.1) was stored happily and the DF then searched the Southern
    # Ocean. Elevation and power are bounded for the same reason: they feed the
    # propagation model directly.
    name: str = Field(min_length=1, max_length=200)
    notes: str = Field("", max_length=4000)
    beacon_lat: float = Field(ge=-90.0, le=90.0)
    beacon_lon: float = Field(ge=-180.0, le=180.0)
    beacon_elev_ft: float = Field(0.0, ge=-1500.0, le=30000.0)
    band: str = Field("121.5", pattern="^(121\\.5|243|406)$")
    # B-5: the exact channel a 406 beacon transmits on. Without it the engine
    # assumes 406.025, which a Becker in Emergency mode always hears, and the
    # coverage difference the two DF heads exist to teach cannot be staged.
    # The COSPAS-SARSAT grid is 406.022-406.076 MHz in 3 kHz steps: 19
    # channels, A through S. Validated against that grid below.
    # Wide enough for every band the console offers (121.5, 243 and 406 MHz);
    # the validator below pins it to the exact channel for the chosen band.
    beacon_freq_hz: int | None = Field(default=None, ge=100_000_000, le=500_000_000)
    power: float = Field(1.0, gt=0.0, le=100.0)
    effects: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_EFFECTS))
    alert_kind: str = Field("", max_length=64)
    alert_text: str = Field("", max_length=2000)
    alert_lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    alert_lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    alert_radius_nm: float | None = Field(default=None, ge=0.0, le=1000.0)

    @model_validator(mode="after")
    def _check_beacon_freq(self):
        if self.beacon_freq_hz is None:
            return self
        if self.band == "406":
            lo, hi, step = 406_022_000, 406_076_000, 3_000
            if not (lo <= self.beacon_freq_hz <= hi
                    and (self.beacon_freq_hz - lo) % step == 0):
                raise ValueError(
                    "beacon_freq_hz must be a COSPAS-SARSAT channel: "
                    "406.022-406.076 MHz in 3 kHz steps")
        else:
            expected = int(float(self.band) * 1_000_000)
            if self.beacon_freq_hz != expected:
                raise ValueError(
                    f"beacon_freq_hz must be {expected} for band {self.band}")
        return self


class SortieIn(BaseModel):
    """Start a sortie. Was an untyped dict, so any key at all was accepted and
    a missing scenario_id became None and then a 404 several frames later."""
    scenario_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=200)


class EffectsIn(BaseModel):
    """Effect toggles an instructor changes mid-exercise (X-6).

    Deliberately a closed set. This used to take a raw dict and merge every key
    of it straight into the scenario row, so a typo did not fail - it was
    stored, forever, in the scenario definition, and every later sortie
    inherited it. Unknown keys are now rejected rather than silently kept.
    """
    model_config = {"extra": "forbid"}

    radio_horizon: bool | None = None
    terrain_masking: bool | None = None
    burst_cadence: bool | None = None
    cone_of_confusion: bool | None = None
    multipath: bool | None = None
    multipath_offset_deg: float | None = Field(default=None, ge=0.0, le=180.0)
    airframe_shadowing: bool | None = None
    df_antenna_profile: str | None = Field(default=None, max_length=64)
    df_antenna_location: str | None = Field(default=None, max_length=16)
    mounting: int | None = Field(default=None, ge=0, le=1)
    antenna_offset_deg: float | None = Field(default=None, ge=-180.0, le=360.0)
    error_code: int | None = Field(default=None, ge=-1, le=12)
    beacon_has_gps: bool | None = None
    wing_null_max_loss_db: float | None = Field(default=None, ge=0.0, le=80.0)
    wing_null_antenna_plane_distance_ft: float | None = Field(default=None, ge=0.0, le=50.0)
    wing_null_half_span_ft: float | None = Field(default=None, ge=0.0, le=200.0)
    wing_null_half_chord_ft: float | None = Field(default=None, ge=0.0, le=50.0)
    wing_null_fuselage_half_width_ft: float | None = Field(default=None, ge=0.0, le=50.0)
    wing_null_fuselage_half_length_ft: float | None = Field(default=None, ge=0.0, le=100.0)
    wing_null_edge_softness_ft: float | None = Field(default=None, ge=0.0, le=50.0)

    def changes(self) -> dict[str, Any]:
        """Only the keys the instructor actually sent."""
        return self.model_dump(exclude_unset=True, exclude_none=True)


CALLSIGN = r"^[A-Za-z0-9 ._-]{2,32}$"


class PositionIn(BaseModel):
    """What the sim bridge POSTs. Phase 4 contract - keep stable.

    The field names and meanings are unchanged; only their accepted ranges are.
    A real report from the plugin has always been inside these.
    """
    model_config = NO_NAN

    callsign: str = Field(pattern=CALLSIGN)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    alt_ft: float = Field(ge=-1500.0, le=60000.0)
    hdg_true: float = Field(0.0, ge=0.0, lt=360.0)
    df: dict[str, Any] | None = None
    # P-11: opt in to the mock DF stub. Only mock_bridge.py sets this. A real
    # station never does, so it can never be handed a fabricated DF picture
    # because its plugin happened to be loading or disabled.
    mock: bool = False


class BearingIn(BaseModel):
    model_config = NO_NAN

    callsign: str = Field(pattern=CALLSIGN)
    bearing_true: float = Field(ge=0.0, lt=360.0)
    note: str = Field("", max_length=500)



class MessageIn(BaseModel):
    """Retasking text. `sender` is set server-side from the caller's session
    where there is one - a base-role client could otherwise sign a message
    "INSTRUCTOR" and it would appear that way on every console (FE-8)."""
    model_config = NO_NAN

    sender: str = Field("MISSION BASE", max_length=64)
    recipient: str = Field("ALL", max_length=64)
    body: str = Field(min_length=1, max_length=2000)



class LoginPayload(BaseModel):
    code: str



class SetupPayload(BaseModel):
    name: str = "Civil Air Patrol SAREX Exercise"
    num_aircraft: int = 1
    aircraft: list[dict] = []
    staff: list[dict] = []


