"""
Request bodies, in one place (C15-1).

X-6 is why these matter: two endpoints took raw dicts, and one of them wrote
whatever it was handed into the scenario definition. Every body the console
accepts is a model now, and they are together so the accepted shape of the
API can be read in one sitting.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .settings import DEFAULT_EFFECTS

class ScenarioIn(BaseModel):
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
    power: float = Field(1.0, gt=0.0, le=100.0)
    effects: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_EFFECTS))
    alert_kind: str = Field("", max_length=64)
    alert_text: str = Field("", max_length=2000)
    alert_lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    alert_lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    alert_radius_nm: float | None = Field(default=None, ge=0.0, le=1000.0)


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


class PositionIn(BaseModel):
    """What the sim bridge POSTs. Phase 4 contract - keep stable."""
    callsign: str
    lat: float
    lon: float
    alt_ft: float
    hdg_true: float = 0.0
    df: dict[str, Any] | None = None
    # P-11: opt in to the mock DF stub. Only mock_bridge.py sets this. A real
    # station never does, so it can never be handed a fabricated DF picture
    # because its plugin happened to be loading or disabled.
    mock: bool = False


class BearingIn(BaseModel):
    callsign: str
    bearing_true: float
    note: str = ""



class MessageIn(BaseModel):
    sender: str = "MISSION BASE"
    recipient: str = "ALL"
    body: str



class LoginPayload(BaseModel):
    code: str



class SetupPayload(BaseModel):
    name: str = "Civil Air Patrol SAREX Exercise"
    num_aircraft: int = 1
    aircraft: list[dict] = []
    staff: list[dict] = []


