"""Flight-test profiles: automated execution of POH test-point techniques.

A POH performance figure is not "fly until something happens". It is the result
of a specific, repeatable technique. A power-off stall speed, for example, is
flown wings level at constant altitude with the power at idle, decelerating at
about one knot per second, and the number recorded is the speed at the break.

This module expresses those techniques as PURE STATE MACHINES. Given an
observation, a profile returns the commands to fly and the phase it is in. It
owns no threads, no sockets and no simulator handles, so every safety rule below
is testable offline and deterministically.

Coupling a profile to control surfaces is the caller's job - see
`direct_backend.XPlaneDirectBackend` for the inner loops. Keeping the decision
logic separate from the actuation is deliberate: the part that decides when to
recover is the part that most needs to be inspectable.

SAFETY MODEL

A stall profile deliberately flies the aircraft to the edge of controlled
flight, which is outside the normal exercise envelope. That is only acceptable
because the profile carries its own, stricter guardrails:

* a high entry floor - recovery altitude, not the routine 1000 ft AGL minimum;
* continuous abort checks on AGL, bank, pitch, altitude loss and elapsed time;
* a recovery that triggers on the break OR on any abort, never only on success;
* recovery that reduces angle of attack FIRST, which is the actual recovery
  action, before adding power.

NOT FLOWN. No profile here has been executed in the simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    STABILIZE = "stabilize"
    DECELERATE = "decelerate"
    RECOVER = "recover"
    COMPLETE = "complete"
    ABORTED = "aborted"


@dataclass(frozen=True)
class Commands:
    """What the profile wants flown this tick."""
    target_pitch_deg: float
    target_roll_deg: float
    throttle: float
    note: str = ""


@dataclass(frozen=True)
class StallLimits:
    """Guardrails for a stall test point. Stricter than the routine envelope."""
    entry_agl_ft: float = 3000.0        # recovery room, not the routine 1000 ft floor
    abort_agl_ft: float = 2000.0
    # Entry criteria are deliberately TIGHTER than the abort criteria. A point
    # that may begin at the same bank angle that would abort it can start at the
    # edge of its own tolerance, and bank angle directly changes the measured
    # stall speed - the POH tabulates 0/30/45/60 degrees as separate columns.
    entry_max_bank_deg: float = 3.0
    entry_max_vs_fpm: float = 100.0
    max_bank_deg: float = 10.0          # abort; the technique is wings level
    max_pitch_deg: float = 25.0
    max_altitude_loss_ft: float = 600.0  # POH notes recovery may cost ~250 ft
    max_seconds: float = 180.0
    stabilize_seconds: float = 5.0
    # break detection
    break_vs_fpm: float = -400.0
    break_min_pitch_deg: float = 4.0
    # recovery
    recovery_pitch_deg: float = 0.0
    recovery_throttle: float = 1.0
    recovery_margin_kts: float = 15.0


@dataclass
class StallTestProfile:
    """Power-off stall to the break, then recover.

    Technique: wings level, hold the entry altitude, power to idle, let the
    aircraft decelerate. The recorded number is the indicated airspeed at the
    break.
    """

    entry_altitude_ft: float
    entry_heading_deg: float
    limits: StallLimits = field(default_factory=StallLimits)

    phase: Phase = Phase.STABILIZE
    break_kias: float | None = None
    abort_reason: str | None = None
    min_kias_seen: float = float("inf")
    _stable_since: float | None = None
    _started: float | None = None

    # -- helpers ----------------------------------------------------------

    def _abort(self, reason: str) -> None:
        self.phase = Phase.ABORTED
        self.abort_reason = reason

    def _abort_check(self, observation, now: float) -> str | None:
        if observation.agl_ft < self.limits.abort_agl_ft:
            return "AGL below abort floor"
        if abs(observation.roll_deg) > self.limits.max_bank_deg:
            return "Bank exceeded test limit"
        if self._started is not None and now - self._started > self.limits.max_seconds:
            return "Test point exceeded time limit"
        lost = self.entry_altitude_ft - observation.altitude_indicated_ft
        if lost > self.limits.max_altitude_loss_ft:
            return "Altitude loss exceeded limit"
        return None

    def _is_break(self, observation, pitch_deg: float) -> bool:
        """A break is a sharp loss of lift at high pitch, not merely slow flight."""
        return (
            observation.vvi_fpm <= self.limits.break_vs_fpm
            and pitch_deg >= self.limits.break_min_pitch_deg
        )

    # -- state machine ----------------------------------------------------

    def step(self, observation, pitch_deg: float, now: float) -> Commands:
        if self.phase in (Phase.COMPLETE, Phase.ABORTED):
            return Commands(
                target_pitch_deg=self.limits.recovery_pitch_deg,
                target_roll_deg=0.0,
                throttle=0.5,
                note=self.phase.value,
            )

        # Aborts outrank everything except an already-finished point. Recovery
        # still runs; aborting is not the same as abandoning the aircraft.
        reason = self._abort_check(observation, now)
        if reason and self.phase is not Phase.RECOVER:
            self._abort(reason)
            return self._recovery_commands("aborting: %s" % reason)

        if self.phase is Phase.STABILIZE:
            return self._stabilize(observation, now)
        if self.phase is Phase.DECELERATE:
            return self._decelerate(observation, pitch_deg, now)
        return self._recover(observation)

    def _stabilize(self, observation, now: float) -> Commands:
        if self._started is None:
            self._started = now
        ready = (
            observation.agl_ft >= self.limits.entry_agl_ft
            and abs(observation.roll_deg) <= self.limits.entry_max_bank_deg
            and abs(observation.vvi_fpm) <= self.limits.entry_max_vs_fpm
            and abs(observation.altitude_indicated_ft - self.entry_altitude_ft) <= 100.0
        )
        if not ready:
            self._stable_since = None
            return Commands(2.0, 0.0, 0.55, "stabilizing")
        if self._stable_since is None:
            self._stable_since = now
        elif now - self._stable_since >= self.limits.stabilize_seconds:
            self.phase = Phase.DECELERATE
            return Commands(3.0, 0.0, 0.0, "power idle, holding altitude")
        return Commands(2.0, 0.0, 0.55, "stabilizing")

    def _decelerate(self, observation, pitch_deg: float, now: float) -> Commands:
        self.min_kias_seen = min(self.min_kias_seen, observation.kias)
        if self._is_break(observation, pitch_deg):
            self.break_kias = self.min_kias_seen
            self.phase = Phase.RECOVER
            return self._recovery_commands("break at %.1f KIAS" % self.break_kias)
        if pitch_deg > self.limits.max_pitch_deg:
            self._abort("Pitch exceeded test limit before a break")
            return self._recovery_commands("aborting: pitch limit")
        # Hold altitude at idle power; angle of attack rises as speed decays.
        # Pitch is commanded gently upward to keep the altitude rather than to
        # force a break, which is what gives the ~1 kt/sec decel rate.
        altitude_error = self.entry_altitude_ft - observation.altitude_indicated_ft
        target_pitch = max(0.0, min(self.limits.max_pitch_deg, 3.0 + altitude_error * 0.02))
        return Commands(target_pitch, 0.0, 0.0, "decelerating")

    def _recovery_commands(self, note: str) -> Commands:
        # Angle of attack first, then power. Adding power at high AoA without
        # unloading is how a stall recovery becomes a secondary stall.
        return Commands(
            target_pitch_deg=self.limits.recovery_pitch_deg,
            target_roll_deg=0.0,
            throttle=self.limits.recovery_throttle,
            note=note,
        )

    def _recover(self, observation) -> Commands:
        recovered = (
            self.break_kias is not None
            and observation.kias >= self.break_kias + self.limits.recovery_margin_kts
            and observation.vvi_fpm > -100.0
            and abs(observation.roll_deg) <= self.limits.max_bank_deg
        )
        if recovered:
            self.phase = Phase.COMPLETE
            return Commands(5.0, 0.0, 0.75, "recovered")
        return self._recovery_commands("recovering")

    # -- result -----------------------------------------------------------

    def result(self) -> dict:
        return {
            "profile": "power_off_stall",
            "phase": self.phase.value,
            "break_kias": self.break_kias,
            "min_kias_seen": None if self.min_kias_seen == float("inf") else self.min_kias_seen,
            "entry_altitude_ft": self.entry_altitude_ft,
            "aborted": self.phase is Phase.ABORTED,
            "abort_reason": self.abort_reason,
        }


def compare_to_target(measured_kias: float | None, target_kias: float,
                      tolerance_kias: float = 3.0) -> dict:
    """Reduce a measured break speed against a POH target.

    Mirrors the dimensional harness: a measured value, a sourced target, a
    tolerance, and a verdict that can be `unmeasured`.
    """
    if measured_kias is None:
        return {"verdict": "unmeasured", "measured_kias": None,
                "target_kias": target_kias, "error_kias": None}
    error = measured_kias - target_kias
    return {
        "verdict": "pass" if abs(error) <= tolerance_kias else "fail",
        "measured_kias": measured_kias,
        "target_kias": target_kias,
        "error_kias": error,
        "tolerance_kias": tolerance_kias,
    }


def scale_stall_speed(target_kias: float, test_weight_lb: float,
                      reference_weight_lb: float = 3100.0) -> float:
    """Stall speed scales with the square root of weight.

    The POH tables are at 3,100 lb. Flying a test point at any other weight
    needs the target scaled, or the comparison is meaningless.
    """
    if reference_weight_lb <= 0 or test_weight_lb <= 0:
        raise ValueError("Weights must be positive")
    return target_kias * (test_weight_lb / reference_weight_lb) ** 0.5
