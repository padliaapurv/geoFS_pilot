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
    def __init__(self, config: dict, trim_elevator_trim_rad: float, trim_throttle_fraction: float, trim_pitch_attitude_rad: float = 0.0):
        gains_cfg = config["autopilot_gains"]
        self.roll_pid = PIDController(PIDGains(**gains_cfg["roll"]), output_limit=1.0)
        self.pitch_pid = PIDController(PIDGains(**gains_cfg["pitch"]), output_limit=1.0)
        self.yaw_damper_kp = gains_cfg["yaw_damper"]["kp"]
        self.speed_pid = PIDController(PIDGains(**gains_cfg["speed"]), output_limit=1.0)
        # Trim values act as the feed-forward bias the loops perturb around.
        self.trim_elevator_trim_rad = trim_elevator_trim_rad
        self.trim_throttle_fraction = trim_throttle_fraction
        self.trim_pitch_attitude_rad = trim_pitch_attitude_rad
        climb_rate_cfg = config.get("climb_rate_to_pitch", {})
        max_pitch_offset_rad = climb_rate_cfg.get("max_pitch_offset_rad", 0.1)
        self.max_pitch_offset_rad = max_pitch_offset_rad
        # A little integral (properly anti-windup bounded to the physically
        # meaningful +-max_pitch_offset_rad, unlike the inner loop's generic
        # +-1 rad) removes the steady-state descent a P-only outer loop
        # otherwise leaves behind. Safe to add now that the P-only response
        # is calm/non-oscillatory -- it wasn't when we tried this earlier
        # against a more aggressive, overshoot-prone outer gain.
        self.climb_rate_to_pitch_pid = PIDController(
            PIDGains(kp=climb_rate_cfg.get("kp", 0.006), ki=climb_rate_cfg.get("ki", 0.0), kd=0.0),
            output_limit=max_pitch_offset_rad,
        )

    def compute_control(self, state, guidance_command: GuidanceCommand, dt: float) -> ControlSurfaceCommand:
        _, pitch_attitude_rad, bank_angle_rad = euler_from_dcm(state.attitude_dcm)
        p_rad_s, q_rad_s, r_rad_s = state.angular_rate_body_rad_s

        roll_error = guidance_command.bank_angle_cmd_rad - bank_angle_rad
        aileron_cmd = self.roll_pid.update(roll_error, p_rad_s, dt)

        # Cascaded altitude hold: climb-rate error sets a small pitch-attitude
        # offset from trim (outer, P-only loop -- deliberately no integral:
        # it wound up badly against this aircraft's real, lightly damped
        # phugoid mode, which our simplified custom model doesn't exhibit),
        # and an inner attitude-hold PID (with pitch-rate damping) drives the
        # elevator. Far more robust than driving elevator directly off
        # climb-rate error, which resonates with the phugoid even harder.
        velocity_ned = state.attitude_dcm @ state.velocity_body_m_s
        climb_rate_m_s = -velocity_ned[2]  # NED down -> climb rate is -Vd
        climb_rate_error = guidance_command.climb_rate_cmd_m_s - climb_rate_m_s
        pitch_offset_cmd = self.climb_rate_to_pitch_pid.update(climb_rate_error, 0.0, dt)
        # Turn compensation: banking reduces the vertical component of lift
        # by cos(bank), so a coordinated turn needs extra AoA/pitch or it
        # bleeds altitude for the whole duration of the turn. Approximate
        # the needed extra pitch as proportional to the trim pitch itself
        # (a proxy for trim CL/CL_alpha) scaled by the load-factor increase.
        load_factor = 1.0 / max(np.cos(bank_angle_rad), 0.4)  # cap near +-65 deg bank
        turn_compensation_rad = self.trim_pitch_attitude_rad * (load_factor - 1.0)

        pitch_attitude_cmd = self.trim_pitch_attitude_rad + pitch_offset_cmd + turn_compensation_rad
        pitch_error = pitch_attitude_cmd - pitch_attitude_rad
        pitch_correction = self.pitch_pid.update(pitch_error, q_rad_s, dt)
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
