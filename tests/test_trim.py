import yaml
import numpy as np
from src.aircraft.aircraft import Aircraft


def load_config():
    with open("config/aircraft_b772.yaml") as f:
        return yaml.safe_load(f)


CRUISE_ALTITUDE_M = 10668.0


def test_trim_hits_target_cl():
    config = load_config()
    aircraft = Aircraft(config)
    aircraft.trim_at(
        altitude_m=CRUISE_ALTITUDE_M, target_cl=0.5,
        position_ned_m=np.array([0.0, 0.0, -CRUISE_ALTITUDE_M]), heading_rad=0.0,
    )

    alpha = aircraft.alpha_rad
    beta = aircraft.beta_rad
    assert np.isclose(beta, 0.0, atol=1e-9)
    assert 0.0 < alpha < np.radians(15.0)

    controls = aircraft.state.controls
    assert controls.aileron_rad == 0.0
    assert controls.rudder_rad == 0.0
    assert 0.0 < controls.throttle_fraction <= 1.0


def test_trim_is_force_balanced_at_first_instant():
    # At the trimmed initial state, with zero angular rates and controls
    # held fixed, net body-frame acceleration should be near zero.
    config = load_config()
    aircraft = Aircraft(config)
    aircraft.trim_at(
        altitude_m=CRUISE_ALTITUDE_M, target_cl=0.5,
        position_ned_m=np.array([0.0, 0.0, -CRUISE_ALTITUDE_M]), heading_rad=0.0,
    )

    state_before = aircraft.state.copy()
    from src.aircraft.state import ControlSurfaceCommand
    from src.atmosphere.wind_field import ZeroWind

    command = ControlSurfaceCommand(
        aileron_rad=0.0, elevator_rad=0.0, rudder_rad=0.0,
        elevator_trim_rad=state_before.controls.elevator_trim_rad,
        throttle_fraction=state_before.controls.throttle_fraction,
    )
    aircraft.step(command, ZeroWind(), dt=0.01)

    d_velocity = (aircraft.state.velocity_body_m_s - state_before.velocity_body_m_s) / 0.01
    assert np.linalg.norm(d_velocity) < 0.5  # m/s^2, small residual acceleration at trim
