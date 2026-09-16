# Alternate outer-loop guidance: fly straight along the initial heading,
# then move to a commanded (lateral, vertical) offset from that original
# track and hold it -- as opposed to Navigator's "go to this (north, east)
# point and stop re-homing" behavior. Same GuidanceCommand output, so it's a
# drop-in swap for Navigator wherever a `.compute(state)` guidance source is
# expected (Autopilot/Simulation code needs zero changes).
#
# The reference track is anchored at wherever the aircraft is when this is
# constructed (its trimmed start position/heading), not at the origin --
# so it works regardless of where trim.initial_position_ned_m points.

import numpy as np
from src.aircraft.geometry import heading_vector_ned, signed_heading_error_rad
from src.guidance.commands import GuidanceCommand


class OffsetNavigator:
    def __init__(self, config: dict, initial_state, cruise_altitude_m: float, cruise_airspeed_m_s: float):
        offset_cfg = config["lateral_offset"]
        self.target_lateral_m = offset_cfg["target_lateral_m"]
        self.target_vertical_m = offset_cfg["target_vertical_m"]
        # Same pure-pursuit law as Navigator (bearing to a point -> heading
        # error -> bank), just re-aimed each step at a synthetic point that's
        # always `lookahead_m` ahead of the aircraft along the reference
        # track, offset laterally by target_lateral_m. This inherits
        # Navigator's proven stability instead of a separate position-error
        # loop stacked on top of the heading loop (tried that first -- a
        # double proportional cascade that overshot and oscillated with no
        # sign of converging, unlike this).
        self.lookahead_m = offset_cfg["lookahead_m"]

        self.max_bank_angle_rad = config["max_bank_angle_rad"]
        self.max_climb_rate_m_s = config["max_climb_rate_m_s"]
        self.heading_kp = config["heading_hold"]["kp_roll_cmd_per_heading_err"]
        self.altitude_kp = config["altitude_hold"]["kp_pitch_cmd_per_alt_err"]

        self.cruise_altitude_m = cruise_altitude_m
        self.cruise_airspeed_m_s = cruise_airspeed_m_s
        self.altitude_target_m = cruise_altitude_m + self.target_vertical_m

        self._origin_ne_m = np.array(initial_state.position_ned_m[:2], dtype=float)
        track_dir = heading_vector_ned(initial_state.attitude_dcm)  # (north, east) unit vector
        self._track_dir = track_dir
        # 90 deg clockwise (i.e. to the right of the direction of travel),
        # consistent with heading increasing clockwise from north.
        self._track_perp_right = np.array([-track_dir[1], track_dir[0]])

        self._latched_arrived = False
        self.arrival_tolerance_m = offset_cfg.get("arrival_tolerance_m", 50.0)

    def compute(self, state) -> GuidanceCommand:
        current_ne = state.position_ned_m[:2] - self._origin_ne_m
        along_track_m = float(np.dot(current_ne, self._track_dir))
        cross_track_m = float(np.dot(current_ne, self._track_perp_right))
        lateral_error_m = self.target_lateral_m - cross_track_m

        # Point at a spot `lookahead_m` further along the track, offset
        # laterally by the full remaining error -- as that error shrinks to
        # zero this converges to just "aim straight down the track."
        virtual_target_ne = (
            (along_track_m + self.lookahead_m) * self._track_dir + self.target_lateral_m * self._track_perp_right
        )
        to_target = virtual_target_ne - current_ne
        desired_heading_vec = to_target / np.linalg.norm(to_target)
        current_heading_vec = heading_vector_ned(state.attitude_dcm)
        heading_error_rad = signed_heading_error_rad(current_heading_vec, desired_heading_vec)
        bank_angle_cmd_rad = float(np.clip(
            self.heading_kp * heading_error_rad, -self.max_bank_angle_rad, self.max_bank_angle_rad,
        ))

        altitude_error_m = self.altitude_target_m - state.altitude_m
        climb_rate_cmd_m_s = float(np.clip(
            self.altitude_kp * altitude_error_m, -self.max_climb_rate_m_s, self.max_climb_rate_m_s,
        ))

        if abs(lateral_error_m) < self.arrival_tolerance_m and abs(altitude_error_m) < self.arrival_tolerance_m:
            self._latched_arrived = True

        # Target point on the offset track abeam the aircraft right now (not
        # the lookahead-shifted virtual_target above) -- what "target vs
        # current position" should actually plot converging together.
        target_ne = self._origin_ne_m + along_track_m * self._track_dir + self.target_lateral_m * self._track_perp_right

        return GuidanceCommand(
            bank_angle_cmd_rad=bank_angle_cmd_rad,
            climb_rate_cmd_m_s=climb_rate_cmd_m_s,
            airspeed_cmd_m_s=self.cruise_airspeed_m_s,
            arrived=self._latched_arrived,
            target_north_m=float(target_ne[0]),
            target_east_m=float(target_ne[1]),
        )
