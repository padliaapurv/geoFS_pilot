# Minimal PID with derivative-on-measurement (avoids derivative kick) and
# integrator anti-windup via output clamping.

from dataclasses import dataclass


@dataclass
class PIDGains:
    kp: float
    ki: float = 0.0
    kd: float = 0.0


class PIDController:
    def __init__(self, gains: PIDGains, output_limit: float = None):
        self.gains = gains
        self.output_limit = output_limit
        self.integral = 0.0

    def reset(self):
        self.integral = 0.0

    def update(self, error: float, measurement_rate: float, dt: float) -> float:
        # measurement_rate: the derivative of the measured (not commanded)
        # process variable, e.g. body rate p/q, used directly for the D term
        # instead of differentiating the error signal.
        candidate_integral = self.integral + error * dt
        output = self.gains.kp * error + self.gains.ki * candidate_integral - self.gains.kd * measurement_rate
        if self.output_limit is not None:
            clipped = max(-self.output_limit, min(self.output_limit, output))
            # Only integrate if not saturated in the direction that would worsen it (anti-windup).
            if clipped == output:
                self.integral = candidate_integral
            return clipped
        self.integral = candidate_integral
        return output
