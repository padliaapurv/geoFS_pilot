# High-level (outer-loop) guidance: "go to this (x, y)". Converts a target
# ground position into a GuidanceCommand (bank angle / climb rate / airspeed)
# for the Autopilot. Knows nothing about control surfaces or aerodynamics.
# Bank angle is capped so the turn toward the target is gentle ("moves
# slowly" toward the new track rather than snapping onto it).

import numpy as np
from src.aircraft.geometry import heading_vector_ned, signed_heading_error_rad
from src.guidance.commands import GuidanceCommand


class Navigator:
    def __init__(self, config: dict, cruise_altitude_m: float, cruise_airspeed_m_s: float):
        self.target_xy_m = np.array(config["target_xy_m"], dtype=float)
        self.arrival_radius_m = config["arrival_radius_m"]
        self.max_bank_angle_rad = config["max_bank_angle_rad"]
        self.max_climb_rate_m_s = config["max_climb_rate_m_s"]
        self.heading_kp = config["heading_hold"]["kp_roll_cmd_per_heading_err"]
        self.altitude_kp = config["altitude_hold"]["kp_pitch_cmd_per_alt_err"]
        self.cruise_altitude_m = cruise_altitude_m
        self.cruise_airspeed_m_s = cruise_airspeed_m_s
        # Once the arrival radius is reached, guidance latches to "arrived"
        # and stops re-homing on the target, so the aircraft flies straight
        # through/past it instead of orbiting back in every time it drifts
        # outside the radius (which would otherwise produce a repeating loop).
        self._latched_arrived = False

    def compute(self, state) -> GuidanceCommand:
        current_xy = state.position_ned_m[:2]
        to_target = self.target_xy_m - current_xy
        distance_m = float(np.linalg.norm(to_target))
        if distance_m < self.arrival_radius_m:
            self._latched_arrived = True
        arrived = self._latched_arrived

        if arrived:
            # Hold current heading (wings level) once arrived, rather than
            # continuing to home on the point.
            bank_angle_cmd_rad = 0.0
        else:
            desired_heading = to_target / distance_m
            current_heading = heading_vector_ned(state.attitude_dcm)
            heading_error_rad = signed_heading_error_rad(current_heading, desired_heading)
            bank_angle_cmd_rad = float(np.clip(
                self.heading_kp * heading_error_rad, -self.max_bank_angle_rad, self.max_bank_angle_rad
            ))

        altitude_error_m = self.cruise_altitude_m - state.altitude_m
        climb_rate_cmd_m_s = float(np.clip(
            self.altitude_kp * altitude_error_m, -self.max_climb_rate_m_s, self.max_climb_rate_m_s
        ))

        return GuidanceCommand(
            bank_angle_cmd_rad=bank_angle_cmd_rad,
            climb_rate_cmd_m_s=climb_rate_cmd_m_s,
            airspeed_cmd_m_s=self.cruise_airspeed_m_s,
            arrived=arrived,
            target_north_m=float(self.target_xy_m[0]),
            target_east_m=float(self.target_xy_m[1]),
        )
