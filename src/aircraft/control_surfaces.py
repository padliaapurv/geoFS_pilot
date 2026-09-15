# Actuator dynamics: first-order lag with rate and position limits, applied
# independently to each control surface / throttle channel.

from dataclasses import dataclass
import numpy as np
from src.aircraft.state import ControlSurfaceState, ControlSurfaceCommand


@dataclass(frozen=True)
class ActuatorLimits:
    position_limit: float
    rate_limit: float
    time_constant_s: float


class ActuatorModel:
    def __init__(self, config: dict):
        self.limits = {
            "aileron_rad": ActuatorLimits(
                config["aileron"]["limit_rad"], config["aileron"]["rate_limit_rad_s"], config["aileron"]["time_constant_s"]
            ),
            "elevator_rad": ActuatorLimits(
                config["elevator"]["limit_rad"], config["elevator"]["rate_limit_rad_s"], config["elevator"]["time_constant_s"]
            ),
            "rudder_rad": ActuatorLimits(
                config["rudder"]["limit_rad"], config["rudder"]["rate_limit_rad_s"], config["rudder"]["time_constant_s"]
            ),
            "elevator_trim_rad": ActuatorLimits(
                config["elevator_trim"]["limit_rad"], config["elevator_trim"]["rate_limit_rad_s"], config["elevator_trim"]["time_constant_s"]
            ),
            "throttle_fraction": ActuatorLimits(
                config["throttle"]["limit_fraction"], config["throttle"]["rate_limit_fraction_s"], config["throttle"]["time_constant_s"]
            ),
        }

    def step(self, current: ControlSurfaceState, command: ControlSurfaceCommand, dt: float) -> ControlSurfaceState:
        new_state = ControlSurfaceState()
        for field_name, limits in self.limits.items():
            current_value = getattr(current, field_name)
            commanded_value = np.clip(getattr(command, field_name), -limits.position_limit, limits.position_limit)
            desired_rate = (commanded_value - current_value) / max(limits.time_constant_s, 1e-6)
            clamped_rate = np.clip(desired_rate, -limits.rate_limit, limits.rate_limit)
            new_value = current_value + clamped_rate * dt
            new_value = np.clip(new_value, -limits.position_limit, limits.position_limit)
            setattr(new_state, field_name, float(new_value))
        # Throttle is a fraction in [0, 1], not symmetric; re-clip explicitly.
        new_state.throttle_fraction = float(np.clip(new_state.throttle_fraction, 0.0, 1.0))
        return new_state
