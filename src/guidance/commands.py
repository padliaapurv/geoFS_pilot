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
