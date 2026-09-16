# Shared command/telemetry types passed between Navigator -> Autopilot -> Aircraft.
# Keeping these in their own module lets any layer be swapped independently
# as long as it still produces/consumes these dataclasses.

from dataclasses import dataclass


@dataclass
class GuidanceCommand:
    # Produced by the high-level Navigator, consumed by the Autopilot.
    bank_angle_cmd_rad: float
    climb_rate_cmd_m_s: float
    airspeed_cmd_m_s: float
    arrived: bool = False
    # Absolute NED target position, for telemetry/plotting only (not used by
    # the Autopilot) -- meaning depends on the navigator: Navigator reports
    # its fixed waypoint; OffsetNavigator reports the point on the target
    # track abeam the aircraft's current along-track position.
    target_north_m: float = 0.0
    target_east_m: float = 0.0
