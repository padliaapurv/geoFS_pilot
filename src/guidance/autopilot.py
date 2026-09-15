# Low-level (inner-loop) autopilot: turns a GuidanceCommand into control
# surface commands. Knows nothing about waypoints or navigation, only about
# holding bank angle, climb rate, and airspeed. Bank/pitch attitude here are
# scalar measurements derived from the DCM (see geometry.euler_from_dcm),
# used purely as loop feedback, not as propagated state.

import numpy as np
from src.aircraft.state import ControlSurfaceCommand
from src.aircraft.geometry import euler_from_dcm
from src.guidance.commands import GuidanceCommand
from src.guidance.pid import PIDController, PIDGains


class Autopilot:
    def __init__(self, config: dict, trim_elevator_trim_rad: float, trim_throttle_fraction: float):
        gains_cfg = config["autopilot_gains"]
        self.roll_pid = PIDController(PIDGains(**gains_cfg["roll"]), output_limit=1.0)
        self.pitch_pid = PIDController(PIDGains(**gains_cfg["pitch"]), output_limit=1.0)
        self.yaw_damper_kp = gains_cfg["yaw_damper"]["kp"]
        self.speed_pid = PIDController(PIDGains(**gains_cfg["speed"]), output_limit=1.0)
        # Trim values act as the feed-forward bias the loops perturb around.
        self.trim_elevator_trim_rad = trim_elevator_trim_rad
        self.trim_throttle_fraction = trim_throttle_fraction

    def compute_control(self, state, guidance_command: GuidanceCommand, dt: float) -> ControlSurfaceCommand:
        _, pitch_attitude_rad, bank_angle_rad = euler_from_dcm(state.attitude_dcm)
        p_rad_s, q_rad_s, r_rad_s = state.angular_rate_body_rad_s

        roll_error = guidance_command.bank_angle_cmd_rad - bank_angle_rad
        aileron_cmd = self.roll_pid.update(roll_error, p_rad_s, dt)

        velocity_ned = state.attitude_dcm @ state.velocity_body_m_s
        climb_rate_m_s = -velocity_ned[2]  # NED down -> climb rate is -Vd
        climb_rate_error = guidance_command.climb_rate_cmd_m_s - climb_rate_m_s
        pitch_correction = self.pitch_pid.update(climb_rate_error, q_rad_s, dt)
        elevator_cmd = -pitch_correction  # nose-up (positive elevator convention: TBD sign, see aero model)

        u, v, w = state.velocity_body_m_s
        beta_rad = np.arctan2(v, np.hypot(u, w))
        rudder_cmd = -self.yaw_damper_kp * r_rad_s - 0.3 * beta_rad

        airspeed_m_s = float(np.linalg.norm(state.velocity_body_m_s))
        speed_error = guidance_command.airspeed_cmd_m_s - airspeed_m_s
        throttle_correction = self.speed_pid.update(speed_error, 0.0, dt)
        throttle_cmd = self.trim_throttle_fraction + throttle_correction

        return ControlSurfaceCommand(
            aileron_rad=float(np.clip(aileron_cmd, -1.0, 1.0)),
            elevator_rad=float(np.clip(elevator_cmd, -1.0, 1.0)),
            rudder_rad=float(np.clip(rudder_cmd, -1.0, 1.0)),
            elevator_trim_rad=self.trim_elevator_trim_rad,
            throttle_fraction=float(np.clip(throttle_cmd, 0.0, 1.0)),
        )
