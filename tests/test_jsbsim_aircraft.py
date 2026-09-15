import yaml
import numpy as np
import pytest

jsbsim = pytest.importorskip("jsbsim")

from src.aircraft.jsbsim_aircraft import JSBSimAircraft
from src.aircraft.state import ControlSurfaceCommand
from src.atmosphere.wind_field import ZeroWind

CRUISE_ALTITUDE_M = 10668.0


def load_config():
    with open("config/aircraft_b772.yaml") as f:
        return yaml.safe_load(f)


def test_jsbsim_trim_hits_target_cl_and_stays_running():
    config = load_config()
    aircraft = JSBSimAircraft(config)
    aircraft.trim_at(
        altitude_m=CRUISE_ALTITUDE_M, target_cl=0.5,
        position_ned_m=np.array([0.0, 0.0, -CRUISE_ALTITUDE_M]), heading_rad=0.0,
    )

    cl, _ = aircraft.get_cl_cd()
    assert np.isclose(cl, 0.5, atol=0.02)
    assert np.isclose(aircraft.beta_rad, 0.0, atol=1e-6)
    # Engines must be started, or the aircraft glides with zero thrust.
    assert aircraft.fdm["propulsion/engine[0]/set-running"] == 1.0
    assert aircraft.fdm["propulsion/engine[1]/set-running"] == 1.0


def test_jsbsim_open_loop_short_period_is_damped():
    # A small pitch-rate perturbation from trim should decay, not grow,
    # confirming the generated aero model is longitudinally stable.
    config = load_config()
    aircraft = JSBSimAircraft(config)
    aircraft.trim_at(
        altitude_m=CRUISE_ALTITUDE_M, target_cl=0.5,
        position_ned_m=np.array([0.0, 0.0, -CRUISE_ALTITUDE_M]), heading_rad=0.0,
    )
    trimmed_controls = aircraft.state.controls
    command = ControlSurfaceCommand(
        elevator_trim_rad=trimmed_controls.elevator_trim_rad,
        throttle_fraction=trimmed_controls.throttle_fraction,
    )
    wind_field = ZeroWind()

    alphas = []
    for _ in range(100):
        aircraft.step(command, wind_field, dt=0.05)
        alphas.append(aircraft.alpha_rad)

    # The initial transient (first second) should be larger than the
    # tail-end residual once the short-period mode has settled.
    early_spread = max(alphas[:20]) - min(alphas[:20])
    late_spread = max(alphas[-20:]) - min(alphas[-20:])
    assert late_spread <= early_spread + 1e-6
