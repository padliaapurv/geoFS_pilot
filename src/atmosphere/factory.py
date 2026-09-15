# Builds a WindField from the wake.yaml config so callers never need to know
# about concrete WindField subclasses.

import numpy as np
from src.atmosphere.wind_field import WindField, ZeroWind, LambOseenVortexPairWake


def build_wind_field(wake_config: dict) -> WindField:
    wake_type = wake_config.get("type", "zero")
    if wake_type == "zero":
        return ZeroWind()
    if wake_type == "lamb_oseen_pair":
        params = wake_config["lamb_oseen_pair"]
        return LambOseenVortexPairWake(
            lead_start_position_ned_m=np.array(params["lead_start_position_ned_m"], dtype=float),
            lead_velocity_ned_m_s=np.array(params["lead_velocity_ned_m_s"], dtype=float),
            lead_wing_span_m=params["lead_wing_span_m"],
            lead_mass_kg=params["lead_mass_kg"],
            core_radius0_m=params["core_radius0_m"],
            core_growth_m2_s=params["core_growth_m2_s"],
            circulation_decay_s=params["circulation_decay_s"],
        )
    raise ValueError(f"Unknown wake type: {wake_type}")
