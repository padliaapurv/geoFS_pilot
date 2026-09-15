# Simple engine model: thrust aligned with body x-axis, lapse with density
# ratio and a mild Mach falloff. No spool-up dynamics beyond the throttle
# actuator lag already applied upstream.

import numpy as np


class EngineModel:
    def __init__(self, config: dict):
        self.num_engines = config["num_engines"]
        self.max_sea_level_thrust_per_engine_n = config["max_sea_level_thrust_per_engine_n"]
        self.thrust_density_exponent = config["thrust_density_exponent"]
        self.thrust_mach_falloff = config["thrust_mach_falloff"]

    def compute_thrust_body_n(self, throttle_fraction: float, density_ratio_sigma: float, mach: float) -> np.ndarray:
        max_thrust_per_engine = (
            self.max_sea_level_thrust_per_engine_n
            * density_ratio_sigma ** self.thrust_density_exponent
            * max(0.0, 1.0 - self.thrust_mach_falloff * mach)
        )
        total_thrust = self.num_engines * max_thrust_per_engine * np.clip(throttle_fraction, 0.0, 1.0)
        return np.array([total_thrust, 0.0, 0.0])
